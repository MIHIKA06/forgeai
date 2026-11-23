"""Stage 1 - intake interviewer: inventory the documents, ask <=5 clarifying questions,
write the structured requirements document, and (optionally) get a human sign-off."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from . import llm
from .docs import Document, _split_sections

MAX_QUESTIONS = 5


def build_inventory(docs: list[Document], log: Callable = print) -> list[dict]:
    inv = []
    for d in docs:
        if d.kind == "table":
            sample = "\n".join(d.text.split("\n")[:15])
            text = f"Table with {d.rows} rows. Columns: {', '.join(d.columns)}\nFirst rows:\n{sample}"
            heads = d.columns
        else:
            words = d.text.split()
            text = " ".join(words[:2200])
            heads = [t for t, _ in _split_sections(d.text) if t][:40]
        try:
            s = llm.chat_json(llm.render("doc_summary", name=d.name, headings=json.dumps(heads), text=text),
                              validate=llm.require_keys("summary", "topics"), max_tokens=600)
        except Exception as e:
            log(f"  ! summary failed for {d.name}: {e}")
            s = {"summary": "", "topics": heads[:10], "doc_type": "other"}
        entry = d.meta()
        entry.update({"summary": s.get("summary", ""), "topics": [str(t) for t in s.get("topics", [])][:15], "doc_type": s.get("doc_type", "other")})
        entry.pop("path", None)
        inv.append(entry)
        log(f"  - {d.name}: {entry['summary'][:110]}")
    return inv


def _inv_text(inventory: list[dict]) -> str:
    lines = []
    for e in inventory:
        size = f"{e['rows']} rows, columns {e['columns']}" if e["kind"] == "table" else f"{e['words']} words"
        lines.append(f"- {e['name']} ({e['kind']}, {size}): {e['summary']} Topics: {', '.join(e['topics'])}")
    return "\n".join(lines)


def interview(brief: str, inventory: list[dict], answers: Optional[dict] = None, interactive: bool = False, log: Callable = print) -> list[dict]:
    """answers: optional {question_index(1-based) or question text: answer} for scripted runs."""
    def _val(d):
        if not isinstance(d, dict) or not isinstance(d.get("questions"), list) or not d["questions"]:
            return "need non-empty 'questions' list"
        return None

    out = llm.chat_json(llm.render("intake_questions", brief=brief, inventory=_inv_text(inventory), max_q=str(MAX_QUESTIONS)), validate=_val, temperature=0.2)
    qs = [q for q in out["questions"] if isinstance(q, dict) and q.get("question")][:MAX_QUESTIONS]  # hard cap, never trust the model
    answers = answers or {}
    result = []
    for i, q in enumerate(qs, 1):
        ans, src = None, "default_assumption"
        if str(i) in answers or i in answers:
            ans, src = answers.get(str(i), answers.get(i)), "requester"
        elif interactive:
            print(f"\n[Q{i}/{len(qs)}] {q['question']}\n      (default if blank: {q.get('default_assumption', '')})")
            try:
                typed = input("  > ").strip()
            except EOFError:
                typed = ""
            if typed:
                ans, src = typed, "requester"
        if ans is None:
            ans = q.get("default_assumption", "No preference; use sensible defaults.")
        result.append({"question": q["question"], "why": q.get("why", ""), "answer": ans, "source": src})
        log(f"  Q{i}: {q['question']}\n      -> [{src}] {ans}")
    return result


def write_requirements(brief: str, inventory: list[dict], clarifications: list[dict]) -> dict:
    def _val(d):
        e = llm.require_keys("agent_name", "purpose", "audience", "tone", "scope", "must_answer_topics", "must_refuse_topics")(d)
        if e:
            return e
        if not isinstance(d["must_answer_topics"], list) or len(d["must_answer_topics"]) < 3:
            return "must_answer_topics needs at least 3 items"
        return None

    clar = "\n".join(f"- Q: {c['question']}\n  A ({c['source']}): {c['answer']}" for c in clarifications) or "(none)"
    req = llm.chat_json(llm.render("requirements", brief=brief, inventory=_inv_text(inventory), clarifications=clar), validate=_val, max_tokens=1500)
    req.setdefault("capabilities_needed", [])
    req.setdefault("answer_format", "short paragraph with source citation")
    req.setdefault("escalation_contact", "the responsible team")
    req["must_answer_topics"] = [str(t) for t in req["must_answer_topics"]][:10]
    # Deterministic completeness check: every explicit ask in the brief must survive into the
    # requirements - otherwise an inconvenient ask (one the docs can't support) silently vanishes
    # and the groundability guard never gets to flag it.
    try:
        asks = llm.chat_json(llm.render("brief_asks", brief=brief), validate=llm.require_keys("asks"), max_tokens=400)["asks"]
    except Exception:
        asks = []
    from .textutil import similarity
    covered_text = " ".join(req["must_answer_topics"] + req.get("capabilities_needed", []) + req["must_refuse_topics"])
    restored = []
    for a in [str(x) for x in asks][:12]:
        if not any(similarity(a, t) >= 0.34 for t in req["must_answer_topics"] + req.get("capabilities_needed", []) + req["must_refuse_topics"]) \
                and similarity(a, covered_text) < 0.5 and len(req["must_answer_topics"]) < 12:
            req["must_answer_topics"].append(a)
            restored.append(a)
    req["brief_asks"] = asks
    req["restored_asks"] = restored
    req["must_refuse_topics"] = [str(t) for t in req["must_refuse_topics"]][:8]
    req["brief"] = brief
    req["clarifications"] = clarifications
    return req


def requirements_markdown(req: dict) -> str:
    g = req.get("groundability", {})
    lines = [f"# Requirements: {req['agent_name']}", "", f"**Purpose:** {req['purpose']}", "",
             f"**Audience:** {req['audience']}", "", f"**Tone:** {req['tone']}", "", f"**Scope:** {req['scope']}", "",
             f"**Answer format:** {req.get('answer_format', '')}", "", f"**Escalation:** {req.get('escalation_contact', '')}", "",
             "## Must-answer topics", ""]
    for t in req["must_answer_topics"]:
        v = g.get("topics", {}).get(t, {})
        badge = {"supported": "SUPPORTED", "partial": "PARTIAL", "unsupported": "UNSUPPORTED - will be refused"}.get(v.get("final"), "")
        lines.append(f"- {t}" + (f"  — **{badge}**" if badge else ""))
    lines += ["", "## Must-refuse topics", ""] + [f"- {t}" for t in req["must_refuse_topics"]]
    lines += ["", "## Capabilities needed", ""] + ([f"- {c}" for c in req.get("capabilities_needed", [])] or ["- (documents only)"])
    if g:
        lines += ["", "## Groundability guard", ""]
        if g.get("warnings"):
            lines += ["> **The brief asks for things the documents cannot support.** These are excluded from the agent's scope and become refusal tests:", ""]
            lines += [f"> - {w}" for w in g["warnings"]]
        else:
            lines.append("All must-answer topics have supporting evidence in the documents.")
        lines += ["", "| Topic | LLM auditor | Deterministic check | Final | Evidence |", "|---|---|---|---|---|"]
        for t, v in g.get("topics", {}).items():
            ev = (v.get("evidence_quote") or "").replace("|", "/")[:90]
            lines.append(f"| {t} | {v.get('llm_verdict')} | {v.get('det_note')} | **{v.get('final')}** | {ev} ({v.get('evidence_doc', '')}) |")
        for c in g.get("capabilities", []):
            if c.get("satisfied_by") == "unsupported":
                lines.append(f"\n- Capability **'{c['capability']}'** cannot be provided: {c.get('reason', '')}")
    lines += ["", "## Clarifications", ""]
    for c in req.get("clarifications", []):
        lines.append(f"- **Q:** {c['question']}\n  - **A ({c['source']}):** {c['answer']}")
    return "\n".join(lines) + "\n"


def human_checkpoint(req: dict, out_dir: Path, interactive: bool, log: Callable = print) -> dict:
    """Stretch goal: requester approves or edits requirements before generation."""
    path = out_dir / "requirements.json"
    if not interactive:
        req["approval"] = {"status": "auto-approved (unattended run)", "edited": False}
        return req
    print("\n" + requirements_markdown(req))
    while True:
        choice = input("Approve requirements? [a]pprove / [e]dit JSON / [q]uit: ").strip().lower() or "a"
        if choice.startswith("a"):
            req["approval"] = {"status": "approved by requester", "edited": req.get("approval", {}).get("edited", False)}
            return req
        if choice.startswith("q"):
            raise SystemExit("Aborted by requester at requirements checkpoint.")
        if choice.startswith("e"):
            editor = os.environ.get("EDITOR", "nano")
            with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
                json.dump({k: v for k, v in req.items() if k not in ("groundability",)}, f, indent=2)
                tmp = f.name
            subprocess.call([editor, tmp])
            try:
                edited = json.loads(Path(tmp).read_text())
                g = req.get("groundability")
                req = edited
                if g:
                    req["groundability"] = g
                req["approval"] = {"status": "edited", "edited": True}
                path.write_text(json.dumps(req, indent=2))
                log("  requirements updated (groundability will be re-checked)")
                req["_needs_recheck"] = True
                return req
            except Exception as e:
                print(f"invalid JSON, edit discarded: {e}")
