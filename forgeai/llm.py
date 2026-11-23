"""Thin, defensive wrapper around any OpenAI-compatible chat endpoint.

Small open models are unreliable at structured output, so every JSON call goes through
`chat_json`: extract -> parse -> validate -> (on failure) show the model its own error and
retry. Every call is metered by the active `Budget` so the factory can stop early.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from openai import OpenAI

from .config import PROMPTS_DIR, SETTINGS


# --------------------------------------------------------------------------- budget
class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_tokens: int = 2_000_000
    max_seconds: float = 3 * 3600
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0
    cache_hits: int = 0
    llm_seconds: float = 0.0
    started: float = field(default_factory=time.time)
    by_stage: dict = field(default_factory=dict)
    stage: str = "misc"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def record(self, tin: int, tout: int, secs: float, cached: bool = False) -> None:
        with self._lock:
            self.calls += 1
            if cached:
                self.cache_hits += 1
            self.tokens_in += tin
            self.tokens_out += tout
            self.llm_seconds += secs
            s = self.by_stage.setdefault(self.stage, {"calls": 0, "tokens": 0, "seconds": 0.0})
            s["calls"] += 1
            s["tokens"] += tin + tout
            s["seconds"] = round(s["seconds"] + secs, 2)

    def remaining_fraction(self) -> float:
        tok = 1 - self.tokens / self.max_tokens
        sec = 1 - (time.time() - self.started) / self.max_seconds
        return max(0.0, min(tok, sec))

    def exhausted(self) -> bool:
        return self.remaining_fraction() <= 0

    def to_dict(self) -> dict:
        return {
            "max_tokens": self.max_tokens,
            "max_seconds": self.max_seconds,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens,
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "llm_seconds": round(self.llm_seconds, 1),
            "wall_seconds": round(time.time() - self.started, 1),
            "by_stage": self.by_stage,
        }


BUDGET = Budget()


def set_budget(b: Budget) -> None:
    global BUDGET
    BUDGET = b


class stage:
    """Context manager to attribute token spend to a pipeline stage."""

    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        self.prev = BUDGET.stage
        BUDGET.stage = self.name

    def __exit__(self, *a):
        BUDGET.stage = self.prev


# --------------------------------------------------------------------------- prompts
def render(template_name: str, **vars: Any) -> str:
    """Load forgeai/prompts/<name>.md and substitute {{var}} placeholders.
    (Double braces so JSON examples inside prompts need no escaping.)"""
    text = (PROMPTS_DIR / f"{template_name}.md").read_text()
    for k, v in vars.items():
        if not isinstance(v, str):
            v = json.dumps(v, indent=2, ensure_ascii=False)
        text = text.replace("{{" + k + "}}", v)
    leftover = re.findall(r"\{\{(\w+)\}\}", text)
    if leftover:
        raise KeyError(f"prompt {template_name} missing vars: {leftover}")
    return text


# --------------------------------------------------------------------------- client
_clients: dict = {}


def client(base_url: Optional[str] = None) -> OpenAI:
    url = base_url or SETTINGS.base_url
    if url not in _clients:
        _clients[url] = OpenAI(base_url=url, api_key=SETTINGS.api_key, timeout=SETTINGS.request_timeout, max_retries=2)
    return _clients[url]


def _cache_path(key: str) -> Path:
    d = SETTINGS.cache_dir / "llm"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def _approx_tokens(s: str) -> int:
    return max(1, len(s) // 4)


def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.0,
    json_mode: bool = False,
    tools: Optional[list] = None,
    max_tokens: int = 1200,
    use_cache: Optional[bool] = None,
) -> dict:
    """Returns {"content": str, "tool_calls": [...], "usage": {...}}."""
    model = model or SETTINGS.model
    use_cache = SETTINGS.use_cache if use_cache is None else use_cache
    payload = {"model": model, "messages": messages, "temperature": temperature, "json": json_mode, "tools": tools, "max_tokens": max_tokens}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]
    cp = _cache_path(key)
    if use_cache and cp.exists():
        out = json.loads(cp.read_text())
        BUDGET.record(out["usage"]["in"], out["usage"]["out"], 0.0, cached=True)
        return out
    if BUDGET.exhausted():
        raise BudgetExceeded(f"budget exhausted: {BUDGET.to_dict()}")

    kwargs: dict = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, seed=SETTINGS.seed)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if tools:
        kwargs["tools"] = tools
    t0 = time.time()
    last_err = None
    for attempt in range(3):
        try:
            resp = client().chat.completions.create(**kwargs)
            break
        except Exception as e:  # network hiccup / rate limit
            last_err = e
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"LLM call failed after retries: {last_err}")
    secs = time.time() - t0
    msg = resp.choices[0].message
    tcs = []
    for tc in msg.tool_calls or []:
        tcs.append({"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments})
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "prompt_tokens", None) or _approx_tokens(json.dumps(messages))
    tout = getattr(usage, "completion_tokens", None) or _approx_tokens(msg.content or "")
    out = {"content": msg.content or "", "tool_calls": tcs, "usage": {"in": tin, "out": tout, "seconds": round(secs, 2)}}
    BUDGET.record(tin, tout, secs)
    if use_cache:
        cp.write_text(json.dumps(out))
    return out


# --------------------------------------------------------------------------- JSON
def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from a messy small-model reply."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # first balanced {...} or [...]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == open_c:
                    depth += 1
                elif ch == close_c:
                    depth -= 1
                    if depth == 0:
                        cand = text[start : i + 1]
                        try:
                            return json.loads(cand)
                        except Exception:
                            # trailing commas are the most common defect
                            try:
                                return json.loads(re.sub(r",\s*([}\]])", r"\1", cand))
                            except Exception:
                                break
            start = text.find(open_c, start + 1)
    raise ValueError("no parseable JSON found")


def chat_json(
    prompt: str,
    validate: Optional[Callable[[Any], Optional[str]]] = None,
    system: str = "You are a precise assistant. Reply with a single valid JSON object and nothing else.",
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 1500,
    retries: int = 2,
) -> Any:
    """Ask for JSON; on parse or validation failure, feed the error back and retry.
    `validate` returns None if OK or an error string describing what is wrong."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    last_err = ""
    for attempt in range(retries + 1):
        r = chat(messages, model=model, temperature=temperature if attempt == 0 else 0.3, json_mode=True, max_tokens=max_tokens)
        try:
            data = extract_json(r["content"])
            err = validate(data) if validate else None
            if not err:
                return data
            last_err = err
        except ValueError as e:
            last_err = str(e)
        messages = messages + [
            {"role": "assistant", "content": r["content"][:3000]},
            {"role": "user", "content": f"That reply was invalid: {last_err}. Reply again with ONLY the corrected JSON object."},
        ]
    raise ValueError(f"chat_json failed after {retries + 1} attempts: {last_err}")


def require_keys(*keys: str) -> Callable[[Any], Optional[str]]:
    def v(d: Any) -> Optional[str]:
        if not isinstance(d, dict):
            return "expected a JSON object"
        missing = [k for k in keys if k not in d]
        return f"missing keys {missing}" if missing else None

    return v


# --------------------------------------------------------------------------- embeddings
def embed(texts: list[str]) -> Optional[list[list[float]]]:
    """Embeddings with an on-disk cache. Returns None if the endpoint does not support them."""
    if not texts:
        return []
    d = SETTINGS.cache_dir / "emb"
    d.mkdir(parents=True, exist_ok=True)
    out: list = [None] * len(texts)
    todo = []
    for i, t in enumerate(texts):
        k = hashlib.sha256((SETTINGS.embed_model + "|" + t).encode()).hexdigest()[:32]
        p = d / f"{k}.json"
        if p.exists():
            out[i] = json.loads(p.read_text())
        else:
            todo.append((i, t, p))
    try:
        c = client(SETTINGS.embed_base_url)
        for s in range(0, len(todo), 32):
            batch = todo[s : s + 32]
            resp = c.embeddings.create(model=SETTINGS.embed_model, input=[t[:6000] for _, t, _ in batch])
            for (i, _, p), item in zip(batch, resp.data):
                out[i] = item.embedding
                p.write_text(json.dumps(item.embedding))
    except Exception:
        return None
    return out
