"""Stage 4 - eval generator. Builds the test set FROM THE DOCUMENTS, then audits it:
every key fact the LLM claims is 'copied from the passage' is verified to really be there,
out-of-scope questions are checked to really be unanswerable (by a different model), and
leaky questions (that contain their own answer) are dropped. The audit trail is saved, so
the eval set itself is evidence, not an act of faith."""
from __future__ import annotations

import csv
import random
import re
from collections import Counter
from pathlib import Path
from typing import Callable

from . import llm
from .config import SETTINGS
from .docs import Chunk, Document
from .retrieval import Index
from .textutil import content_words, fact_in_text, numbers, quote_in_text, similarity

TARGETS = {"answerable": 12, "multi_doc": 3, "ambiguous": 3, "out_of_scope": 5, "gap_probe": 3, "tool": 3}


class Audit:
    def __init__(self):
        self.events = []

    def drop(self, kind: str, q: str, reason: str):
        self.events.append({"kind": kind, "question": q, "action": "dropped", "reason": reason})

    def fix(self, kind: str, q: str, reason: str):
        self.events.append({"kind": kind, "question": q, "action": "repaired", "reason": reason})

    def summary(self) -> dict:
        c = Counter((e["kind"], e["action"]) for e in self.events)
        return {f"{k}:{a}": n for (k, a), n in c.items()}


def _verify_facts(facts: list, passage: str) -> list[str]:
    ok = []
    for f in facts or []:
        f = str(f).strip().strip('"').strip()
        if 1 <= len(f.split()) <= 14 and (quote_in_text(f, passage, 0.85) or fact_in_text(f, passage, 0.9)):
            ok.append(f)
    return ok


def _leaky(question: str, facts: list[str]) -> bool:
    """Question already contains its answer (all fact numbers + most words)."""
    for f in facts:
        fw = set(content_words(f))
        if fw and len(fw & set(content_words(question))) / len(fw) < 0.8:
            return False
        if numbers(f) and not numbers(f) <= numbers(question):
            return False
    return True


def _pick_chunks(chunks: list[Chunk], index: Index, topics: list[str], n: int, rng: random.Random) -> list[Chunk]:
    """Coverage-driven: one chunk per supported topic first, then round-robin across documents."""
    good = [c for c in chunks if len(c.text.split()) >= 35 and c.section != "row"]
    picked, seen = [], set()
    for t in topics:
        for c, _ in index.search(t, top_k=3, mode="bm25"):
            if c.id not in seen and c in good:
                picked.append(c)
                seen.add(c.id)
                break
    by_doc: dict = {}
    for c in good:
        by_doc.setdefault(c.doc, []).append(c)
    for lst in by_doc.values():
        rng.shuffle(lst)
    while len(picked) < n and any(by_doc.values()):
        for d in list(by_doc):
            if by_doc[d]:
                c = by_doc[d].pop()
                if c.id not in seen:
                    picked.append(c)
                    seen.add(c.id)
            if len(picked) >= n:
                break
    return picked[:n]


def gen_answerable(chunks, index, req, n, rng, audit, log) -> list[dict]:
    out = []
    pool = _pick_chunks(chunks, index, req.get("supported_topics", req["must_answer_topics"]), n + 5, rng)
    for c in pool:
        if len(out) >= n:
            break
        try:
            r = llm.chat_json(llm.render("evalgen_answerable", audience=req["audience"], doc=c.doc, passage=c.text, n="1"),
                              validate=llm.require_keys("cases"), temperature=0.3, max_tokens=500)
        except Exception as e:
            audit.drop("answerable", "", f"generation failed: {e}")
            continue
        for case in r.get("cases", [])[:1]:
            q = str(case.get("question", "")).strip()
            facts = _verify_facts(case.get("key_facts"), c.text)
            if not q:
                continue
            if not facts:
                audit.drop("answerable", q, f"none of the claimed key facts {case.get('key_facts')} appear in the source passage")
                continue
            if len(facts) < len(case.get("key_facts") or []):
                audit.fix("answerable", q, f"removed unverifiable key facts; kept {facts}")
            if _leaky(q, facts):
                audit.drop("answerable", q, "question contains its own answer")
                continue
            if any(similarity(q, o["question"]) > 0.7 for o in out):
                audit.drop("answerable", q, "near-duplicate question")
                continue
            out.append({"type": "answerable", "question": q, "expected_behavior": "answer", "expected_sources": [c.doc],
                        "source_chunks": [c.id], "key_facts": facts, "reference_answer": case.get("reference_answer", ""),
                        "generated_by": "evalgen_answerable"})
    log(f"  answerable: {len(out)}")
    return out


def gen_multidoc(chunks, index, req, n, rng, audit, log) -> list[dict]:
    docs = sorted({c.doc for c in chunks if c.section != "row"})
    if len(docs) < 2:
        log("  multi_doc: skipped (single document)")
        return []
    good = [c for c in chunks if len(c.text.split()) >= 35 and c.section != "row"]
    rng.shuffle(good)
    pairs, used = [], set()
    for a in good:
        for b, s in index.search(a.text[:600], top_k=12, mode="bm25"):
            if b.doc != a.doc and b.section != "row" and len(b.text.split()) >= 35 and (a.doc, b.doc) not in used:
                pairs.append((a, b))
                used.add((a.doc, b.doc))
                used.add((b.doc, a.doc))
                break
        if len(pairs) >= n + 2:
            break
    out = []
    for a, b in pairs:
        if len(out) >= n:
            break
        try:
            r = llm.chat_json(llm.render("evalgen_multidoc", audience=req["audience"], doc_a=a.doc, doc_b=b.doc, passage_a=a.text, passage_b=b.text),
                              validate=llm.require_keys("question"), temperature=0.3, max_tokens=500)
        except Exception:
            continue
        q = str(r.get("question", "")).strip()
        if not q:
            audit.drop("multi_doc", f"{a.doc}+{b.doc}", "generator found no sensible combined question")
            continue
        f1, f2 = _verify_facts(r.get("key_facts_1"), a.text), _verify_facts(r.get("key_facts_2"), b.text)
        if not f1 or not f2:
            audit.drop("multi_doc", q, "key facts not verified in BOTH passages")
            continue
        out.append({"type": "multi_doc", "question": q, "expected_behavior": "answer", "expected_sources": [a.doc, b.doc],
                    "source_chunks": [a.id, b.id], "key_facts": f1 + f2, "reference_answer": r.get("reference_answer", ""),
                    "generated_by": "evalgen_multidoc"})
    log(f"  multi_doc: {len(out)}")
    return out


def gen_ambiguous(base: list[dict], n, rng, audit, log) -> list[dict]:
    out = []
    cands = base[:]
    rng.shuffle(cands)
    for b in cands:
        if len(out) >= n:
            break
        try:
            r = llm.chat_json(llm.render("evalgen_ambiguous", question=b["question"], facts="; ".join(b["key_facts"])),
                              validate=llm.require_keys("question"), temperature=0.6, max_tokens=250)
        except Exception:
            continue
        q = str(r.get("question", "")).strip()
        if not q or similarity(q, b["question"]) > 0.75:
            audit.drop("ambiguous", q or b["question"], "rewrite too close to original")
            continue
        if _leaky(q, b["key_facts"]):
            audit.drop("ambiguous", q, "rewrite leaks the answer")
            continue
        out.append({**{k: v for k, v in b.items() if k not in ("question", "type", "generated_by")}, "type": "ambiguous", "question": q,
                    "derived_from": b["question"], "ambiguity": r.get("ambiguity", ""), "generated_by": "evalgen_ambiguous"})
    log(f"  ambiguous: {len(out)}")
    return out


def _docs_answer(question: str, index: Index) -> tuple[bool, str]:
    hits = index.search(question, top_k=4, mode="hybrid")
    ptxt = "\n\n".join(f"[{c.doc}] {c.text[:700]}" for c, _ in hits)
    try:
        r = llm.chat_json(llm.render("oos_verify", question=question, passages=ptxt), validate=llm.require_keys("answerable"),
                          model=SETTINGS.judge_model, max_tokens=200)
        return bool(r.get("answerable")), str(r.get("reason", ""))
    except Exception as e:
        return False, f"verifier failed ({e})"


def gen_oos(index, req, inventory, n, audit, log) -> list[dict]:
    covered = sorted({t for e in inventory for t in e.get("topics", [])})[:30]
    try:
        r = llm.chat_json(llm.render("evalgen_oos", purpose=req["purpose"], audience=req["audience"], refuse=", ".join(req["must_refuse_topics"]),
                                     covered=", ".join(covered), n=str(n + 4)), validate=llm.require_keys("cases"), temperature=0.5, max_tokens=900)
    except Exception as e:
        log(f"  ! oos generation failed: {e}")
        return []
    out = []
    for c in r.get("cases", []):
        if len(out) >= n or not isinstance(c, dict):
            continue
        q = str(c.get("question", "")).strip()
        if not q:
            continue
        kind = "must_refuse" if c.get("type") == "must_refuse" else "adjacent"
        # verify BOTH kinds: a 'must refuse' question the documents answer is a contradictory test
        ans, why = _docs_answer(q, index)
        if ans:
            audit.drop("out_of_scope", q, f"documents actually answer it ({kind}): {why}")
            continue
        out.append({"type": "out_of_scope", "subtype": kind, "question": q, "expected_behavior": "refuse", "expected_sources": [],
                    "key_facts": [], "topic": c.get("topic", ""), "generated_by": "evalgen_oos"})
    log(f"  out_of_scope: {len(out)}")
    return out


def gen_gap_probes(index, req, n, audit, log) -> list[dict]:
    gaps = req.get("known_gaps", [])
    g = req.get("groundability", {}).get("topics", {})
    out = []
    for topic in gaps:
        if len(out) >= n:
            break
        try:
            r = llm.chat_json(llm.render("evalgen_gap", purpose=req["purpose"], topic=topic, missing=g.get(topic, {}).get("missing", ""), n="1"),
                              validate=llm.require_keys("questions"), temperature=0.4, max_tokens=300)
        except Exception:
            continue
        for q in r.get("questions", [])[:1]:
            q = str(q).strip()
            ans, why = _docs_answer(q, index)
            if ans:
                audit.drop("gap_probe", q, f"documents answer it after all: {why}")
                continue
            out.append({"type": "gap_probe", "question": q, "expected_behavior": "refuse", "expected_sources": [], "key_facts": [],
                        "topic": topic, "generated_by": "evalgen_gap"})
    log(f"  gap_probe: {len(out)}")
    return out


def _num(v: str):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def gen_tool_cases(docs: list[Document], tool_names: list[str], n, rng, audit, log) -> list[dict]:
    tables = [d for d in docs if d.kind == "table"]
    if not tables or not ({"csv_lookup", "calculator"} & set(tool_names)):
        return []
    out = []
    d = tables[0]
    with open(d.path, newline="", encoding="utf-8", errors="ignore") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    cols = list(rows[0].keys())
    id_col = cols[0]
    numeric = [c for c in cols[1:] if all(_num(r.get(c, "")) is not None for r in rows[:20])]
    price_col = next((c for c in numeric if re.search(r"price|cost|rate|usd|eur|amount", c, re.I)), None)
    sample = rng.sample(rows, min(len(rows), n + 3))
    for i, row in enumerate(sample):
        if len(out) >= n:
            break
        use_calc = "calculator" in tool_names and price_col and i % 2 == 1
        if use_calc:
            qty = rng.randint(3, 12)
            total = round(qty * _num(row[price_col]), 2)
            extra = f"The question must ask for the total {price_col} for buying {qty} units of this item."
            col, value, facts = price_col, str(total), [f"{total:g}" if total != int(total) else str(int(total))]
        else:
            targets = [c for c in numeric if c != id_col] or cols[1:]
            col = rng.choice(targets)
            value, facts, extra = row[col], [row[col]], ""
        try:
            r = llm.chat_json(llm.render("evalgen_table", column=col, value=value, row=str(row), extra=extra),
                              validate=llm.require_keys("question"), temperature=0.4, max_tokens=200)
        except Exception:
            continue
        q = str(r.get("question", "")).strip()
        if not q or (str(value) in q):
            audit.drop("tool", q, "empty or leaks the value")
            continue
        out.append({"type": "tool", "question": q, "expected_behavior": "answer", "expected_sources": [d.name], "key_facts": facts,
                    "requires_tool": "calculator" if use_calc else "csv_lookup", "row_id": row[id_col],
                    "generated_by": "evalgen_table", "note": f"expected value computed deterministically from row {row[id_col]}"})
    log(f"  tool: {len(out)}")
    return out


def assign_split(cases: list[dict], rng: random.Random, holdout_frac: float = 0.3) -> None:
    by: dict = {}
    for c in cases:
        by.setdefault(c["type"], []).append(c)
    for t, lst in by.items():
        rng.shuffle(lst)
        k = int(round(len(lst) * holdout_frac)) if len(lst) >= 3 else 0
        for i, c in enumerate(lst):
            c["split"] = "holdout" if i < k else "dev"


def generate_evalset(docs, chunks, index, req, inventory, tool_names, log: Callable = print, targets=None, seed: int = 13) -> dict:
    t = dict(TARGETS, **(targets or {}))
    rng = random.Random(seed)
    audit = Audit()
    ans = gen_answerable(chunks, index, req, t["answerable"], rng, audit, log)
    multi = gen_multidoc(chunks, index, req, t["multi_doc"], rng, audit, log)
    amb = gen_ambiguous(ans, t["ambiguous"], rng, audit, log)
    oos = gen_oos(index, req, inventory, t["out_of_scope"], audit, log)
    gaps = gen_gap_probes(index, req, t["gap_probe"], audit, log)
    tool = gen_tool_cases(docs, tool_names, t["tool"], rng, audit, log)
    cases = ans + multi + amb + oos + gaps + tool
    # top-up to guarantee >= 20 cases on small corpora
    tries = 0
    while len(cases) < 20 and tries < 3:
        tries += 1
        more = gen_answerable(chunks, index, req, 20 - len(cases), random.Random(seed + tries), audit, log)
        more = [m for m in more if all(similarity(m["question"], c["question"]) <= 0.7 for c in cases)]
        cases += more
    prefix = {"answerable": "A", "multi_doc": "M", "ambiguous": "E", "out_of_scope": "O", "gap_probe": "G", "tool": "T"}
    counts: Counter = Counter()
    for c in cases:
        counts[c["type"]] += 1
        c["id"] = f"{prefix[c['type']]}{counts[c['type']]:02d}"
    assign_split(cases, rng)
    cases.sort(key=lambda c: c["id"])
    return {"cases": cases, "counts": dict(Counter(c["type"] for c in cases)), "splits": dict(Counter(c["split"] for c in cases)),
            "audit": {"summary": audit.summary(), "events": audit.events},
            "prompts": ["evalgen_answerable", "evalgen_multidoc", "evalgen_ambiguous", "evalgen_oos", "evalgen_gap", "evalgen_table", "oos_verify"]}
