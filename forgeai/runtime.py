"""Generic agent runner. Loads ANY ForgeAI agent definition (agent.json) and answers
questions with retrieval + optional tools under a JSON output contract.

This is the "runnable product": the factory's output is pure data, this file executes it.
"""
from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path
from typing import Optional

from . import llm, tools
from .docs import chunk_documents, load_folder
from .retrieval import Index

SCHEMA_VERSION = "forgeai/agent@1"

DEFAULT_RETRIEVAL = {"strategy": "section", "chunk_size": 220, "chunk_overlap": 40, "top_k": 5, "mode": "hybrid", "query_rewrite": False}
DEFAULT_CONTRACT = {
    "format": "json",
    "fields": {"answer": "string", "citations": "list of passage labels", "refused": "boolean"},
    "max_words": 160,
    "citation_required": True,
    "refusal_message": "I'm sorry, that is outside what I can answer from the documents I have. Please contact the responsible team.",
}


def validate_definition(d: dict) -> list[str]:
    errs = []
    for k in ("name", "system_prompt", "retrieval", "tools", "output_contract", "knowledge"):
        if k not in d:
            errs.append(f"missing '{k}'")
    if "retrieval" in d:
        r = d["retrieval"]
        if not (1 <= int(r.get("top_k", 0)) <= 20):
            errs.append("retrieval.top_k must be 1..20")
        if r.get("mode") not in ("bm25", "dense", "hybrid"):
            errs.append("retrieval.mode must be bm25|dense|hybrid")
    for t in d.get("tools", []):
        if t.get("name") not in tools.REGISTRY:
            errs.append(f"unknown tool {t.get('name')}")
    return errs


def contract_block(c: dict) -> str:
    return (
        "## Output contract (mandatory)\n"
        "Reply with exactly ONE JSON object and nothing else:\n"
        '{"answer": "<your answer>", "citations": ["S1"], "refused": false}\n'
        f"- answer: plain text, at most {c.get('max_words', 160)} words.\n"
        "- citations: the labels of the CONTEXT passages [S#] or TOOL results [T#] you used. "
        + ("Must be non-empty whenever refused is false.\n" if c.get("citation_required", True) else "\n")
        + "- Only use facts that appear in the CONTEXT or TOOL results. Never invent numbers, names or rules.\n"
        f'- If the question is out of scope or the CONTEXT does not contain the answer, reply: {{"answer": "{c.get("refusal_message", DEFAULT_CONTRACT["refusal_message"])}", "citations": [], "refused": true}}'
    )


class Agent:
    def __init__(self, definition: dict, base_dir: Optional[Path] = None, use_cache: Optional[bool] = None):
        self.d = copy.deepcopy(definition)
        self.d.setdefault("retrieval", {})
        for k, v in DEFAULT_RETRIEVAL.items():
            self.d["retrieval"].setdefault(k, v)
        self.d.setdefault("output_contract", {})
        for k, v in DEFAULT_CONTRACT.items():
            self.d["output_contract"].setdefault(k, v)
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.use_cache = use_cache
        kp = Path(self.d["knowledge"]["docs_path"])
        self.docs_path = kp if kp.is_absolute() else (self.base_dir / kp)
        self.docs = load_folder(self.docs_path)
        r = self.d["retrieval"]
        self.chunks = chunk_documents(self.docs, r["strategy"], int(r["chunk_size"]), int(r["chunk_overlap"]))
        self.index = Index(self.chunks, use_dense=r["mode"] != "bm25")
        self.tool_names = [t["name"] for t in self.d.get("tools", [])]
        tools.set_csv_files([d.path for d in self.docs if d.kind == "table"])

    @classmethod
    def load(cls, path: str | Path, **kw) -> "Agent":
        p = Path(path)
        return cls(json.loads(p.read_text()), base_dir=p.parent, **kw)

    # ------------------------------------------------------------------ helpers
    def _rewrite(self, q: str) -> list[str]:
        try:
            out = llm.chat_json(
                f"Rewrite this user question into 2 alternative search queries that use different wording "
                f"(synonyms, formal policy terms). Question: {q}\nReturn JSON: {{\"queries\": [\"...\", \"...\"]}}",
                validate=llm.require_keys("queries"), max_tokens=200,
            )
            return [s for s in out["queries"] if isinstance(s, str)][:2]
        except Exception:
            return []

    def retrieve(self, question: str) -> list[dict]:
        r = self.d["retrieval"]
        extra = self._rewrite(question) if r.get("query_rewrite") else []
        hits = self.index.search(question, int(r["top_k"]), r["mode"], extra)
        return [{"label": f"S{i+1}", "chunk_id": c.id, "doc": c.doc, "section": c.section, "text": c.text, "score": round(s, 4)} for i, (c, s) in enumerate(hits)]

    # ------------------------------------------------------------------ main entry
    def answer(self, question: str, history: Optional[list[dict]] = None) -> dict:
        t0 = time.time()
        tok0 = llm.BUDGET.tokens
        passages = self.retrieve(question)
        ctx = "\n\n".join(f"[{p['label']}] (source: {p['doc']}{' > ' + p['section'] if p['section'] else ''})\n{p['text']}" for p in passages)
        system = self.d["system_prompt"].strip() + "\n\n" + contract_block(self.d["output_contract"])
        if self.tool_names:
            system += "\n\n## Tools\nYou may call the provided tools when the CONTEXT alone is not enough (exact lookups, arithmetic, dates). Cite tool results as T1, T2... in call order."
        msgs = [{"role": "system", "content": system}]
        for turn in (history or [])[-6:]:
            msgs.append({"role": turn["role"], "content": turn["content"]})
        msgs.append({"role": "user", "content": f"CONTEXT:\n{ctx or '(no passages found)'}\n\nQUESTION: {question}"})

        temp = float(self.d.get("generation", {}).get("temperature", 0.1))
        model = self.d.get("generation", {}).get("model")
        tool_results: list[dict] = []
        violations: list[str] = []
        content = ""
        if self.tool_names:
            schemas = [tools.REGISTRY[n].schema() for n in self.tool_names]
            for _round in range(3):
                r = llm.chat(msgs, model=model, temperature=temp, tools=schemas, max_tokens=700, use_cache=self.use_cache)
                if not r["tool_calls"]:
                    content = r["content"]
                    break
                msgs.append({"role": "assistant", "content": r["content"] or "", "tool_calls": [
                    {"id": tc["id"] or f"call_{i}", "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for i, tc in enumerate(r["tool_calls"])]})
                for i, tc in enumerate(r["tool_calls"]):
                    if tc["name"] not in self.tool_names:
                        res = {"error": f"tool {tc['name']} is not attached to this agent"}
                        violations.append(f"called unattached tool {tc['name']}")
                    else:
                        res = tools.run_tool(tc["name"], tc["arguments"])
                    label = f"T{len(tool_results)+1}"
                    tool_results.append({"label": label, "tool": tc["name"], "args": tc["arguments"], "result": res})
                    msgs.append({"role": "tool", "tool_call_id": tc["id"] or f"call_{i}", "content": f"[{label}] " + json.dumps(res)[:3000]})
            else:
                msgs.append({"role": "user", "content": "Stop calling tools. Answer now using the JSON contract."})
                content = llm.chat(msgs, model=model, temperature=temp, json_mode=True, max_tokens=700, use_cache=self.use_cache)["content"]
        else:
            content = llm.chat(msgs, model=model, temperature=temp, json_mode=True, max_tokens=700, use_cache=self.use_cache)["content"]

        parsed = self._parse(content, violations, msgs, model)
        labels = {p["label"]: p for p in passages}
        tlabels = {t["label"]: t for t in tool_results}
        cites, bad = [], []
        for c in parsed.get("citations") or []:
            c = str(c).strip().strip("[]")
            if c in labels or c in tlabels:
                cites.append(c)
            else:
                bad.append(c)
        if bad:
            violations.append(f"invalid citation labels {bad}")
        answer = str(parsed.get("answer", "")).strip()
        refused = bool(parsed.get("refused", False))
        if not refused and self.d["output_contract"].get("citation_required", True) and not cites:
            violations.append("answer without citations")
        mw = int(self.d["output_contract"].get("max_words", 160))
        if len(answer.split()) > mw * 1.5:
            violations.append(f"answer exceeds max_words ({len(answer.split())}>{mw})")
        return {
            "question": question,
            "answer": answer,
            "refused": refused,
            "citations": cites,
            "cited_docs": sorted({labels[c]["doc"] for c in cites if c in labels} | {f"tool:{tlabels[c]['tool']}" for c in cites if c in tlabels}),
            "passages": passages,
            "tool_results": tool_results,
            "contract_violations": violations,
            "raw": content[:2000],
            "latency_s": round(time.time() - t0, 2),
            "tokens": llm.BUDGET.tokens - tok0,
        }

    def _parse(self, content: str, violations: list, msgs: list, model) -> dict:
        try:
            d = llm.extract_json(content)
            if isinstance(d, dict) and "answer" in d:
                return d
        except ValueError:
            pass
        violations.append("output was not valid contract JSON (repaired)")
        try:
            fix = llm.chat(
                [{"role": "system", "content": "Convert the draft into the JSON contract {\"answer\": str, \"citations\": [labels], \"refused\": bool}. Keep the meaning. JSON only."},
                 {"role": "user", "content": content[:3000] or "(empty)"}],
                model=model, json_mode=True, max_tokens=600, use_cache=self.use_cache,
            )["content"]
            d = llm.extract_json(fix)
            if isinstance(d, dict) and "answer" in d:
                return d
        except Exception:
            pass
        # last resort: treat raw text as the answer, recover [S#] labels
        return {"answer": content.strip(), "citations": re.findall(r"\b([ST]\d+)\b", content), "refused": False}
