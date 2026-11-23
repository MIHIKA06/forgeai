"""Stage 2 - groundability guard. For every must-answer topic, an LLM auditor reads the best
passages and gives a verdict + an evidence quote; a deterministic check then verifies the
quote really exists in those passages and that the topic's words actually occur there.
The final verdict is the MORE PESSIMISTIC of the two. Unsupported topics are removed from
the agent's scope and turned into refusal tests, so the generated agent cannot
'hallucinate the gap away'."""
from __future__ import annotations

import json
from typing import Callable

from . import llm, tools
from .retrieval import Index
from .textutil import content_words, quote_in_text

ORDER = {"unsupported": 0, "partial": 1, "supported": 2}


def _topic_coverage(topic: str, passages: list[str]) -> float:
    tw = set(content_words(topic))
    if not tw:
        return 1.0
    pw = set(content_words(" ".join(passages)))
    stem = lambda w: w[:5]
    return len({stem(w) for w in tw} & {stem(w) for w in pw}) / len({stem(w) for w in tw})


def check_topics(req: dict, index: Index, log: Callable = print) -> dict:
    results = {}
    for topic in req["must_answer_topics"]:
        hits = index.search(f"{topic}", top_k=5, mode="hybrid")
        ptxt = "\n\n".join(f"[P{i+1}] ({c.doc}) {c.text[:900]}" for i, (c, _) in enumerate(hits))
        try:
            v = llm.chat_json(llm.render("groundability", topic=topic, purpose=req["purpose"], passages=ptxt),
                              validate=llm.require_keys("verdict"), max_tokens=400)
        except Exception as e:
            v = {"verdict": "partial", "evidence_quote": "", "missing": f"auditor failed: {e}"}
        llm_v = str(v.get("verdict", "partial")).lower().strip()
        if llm_v not in ORDER:
            llm_v = "partial"
        quote = str(v.get("evidence_quote", "") or "")
        texts = [c.text for c, _ in hits]
        quote_ok = bool(quote) and any(quote_in_text(quote, t) for t in texts)
        coverage = _topic_coverage(topic, texts[:3])
        # deterministic upper bound on the verdict
        if quote_ok and coverage >= 0.5:
            det, note = "supported", f"quote verified, coverage {coverage:.0%}"
        elif quote_ok or coverage >= 0.5:
            det, note = "partial", ("quote verified" if quote_ok else "quote NOT found") + f", coverage {coverage:.0%}"
        else:
            det, note = "unsupported", ("no quote" if not quote else "quote NOT found in passages") + f", coverage {coverage:.0%}"
        final = min(llm_v, det, key=lambda x: ORDER[x])
        evidence_doc = ""
        if quote_ok:
            evidence_doc = next((c.doc for c, _ in hits if quote_in_text(quote, c.text)), "")
        results[topic] = {"llm_verdict": llm_v, "det_verdict": det, "det_note": note, "final": final,
                          "evidence_quote": quote if quote_ok else "", "evidence_doc": evidence_doc,
                          "missing": v.get("missing", ""), "top_docs": sorted({c.doc for c, _ in hits[:3]})}
        log(f"  [{final.upper():11}] {topic}  (llm={llm_v}; {note})")
    return results


def check_capabilities(req: dict, files: list[str], log: Callable = print) -> list[dict]:
    caps = [c for c in req.get("capabilities_needed", []) if str(c).strip()]
    if not caps:
        return []
    tool_txt = "\n".join(f"- {t.name}: {t.description}" for t in tools.REGISTRY.values())
    try:
        out = llm.chat_json(llm.render("capability_check", tools=tool_txt, files=", ".join(files), capabilities=json.dumps(caps)),
                            validate=llm.require_keys("mapping"), max_tokens=700)
        mapping = [m for m in out["mapping"] if isinstance(m, dict)]
    except Exception:
        mapping = [{"capability": c, "satisfied_by": "documents", "reason": "capability check failed; assumed documents"} for c in caps]
    for m in mapping:
        sb = str(m.get("satisfied_by", "documents"))
        if sb not in tools.REGISTRY and sb not in ("documents", "unsupported"):
            m["satisfied_by"] = "unsupported" if "unsupported" in sb.lower() else "documents"
        log(f"  capability '{m.get('capability')}' -> {m['satisfied_by']}")
    return mapping


def run_guard(req: dict, index: Index, files: list[str], log: Callable = print) -> dict:
    topics = check_topics(req, index, log)
    caps = check_capabilities(req, files, log)
    warnings, gaps = [], []
    for t, v in topics.items():
        if v["final"] == "unsupported":
            warnings.append(f"Topic '{t}' is not supported by the documents ({v['missing'] or v['det_note']}).")
            gaps.append(t)
    for c in caps:
        if c["satisfied_by"] == "unsupported":
            warnings.append(f"Capability '{c['capability']}' cannot be provided by documents or tools ({c.get('reason', '')}).")
            gaps.append(c["capability"])
    n = len(topics) or 1
    supported = sum(1 for v in topics.values() if v["final"] != "unsupported")
    g = {"topics": topics, "capabilities": caps, "warnings": warnings, "known_gaps": gaps,
         "coverage": round(supported / n, 2),
         "status": "ok" if not warnings else ("blocked" if supported / n < 0.5 else "gaps_flagged")}
    return g


def apply_guard(req: dict, g: dict) -> dict:
    """Move unsupported topics out of scope: they become refusal topics with a reason."""
    req["groundability"] = g
    gap_topics = [t for t in req["must_answer_topics"] if g["topics"].get(t, {}).get("final") == "unsupported"]
    req["supported_topics"] = [t for t in req["must_answer_topics"] if t not in gap_topics]
    req["known_gaps"] = g["known_gaps"]
    return req
