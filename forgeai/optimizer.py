"""Stage 6 - critic/optimizer loop.

run evals -> classify failures (retrieval_miss / prompt_defect / hallucination / wrong_refusal)
-> ONE targeted fix per failing category (retrieval params, or a single prompt section)
-> re-run the FULL dev set -> accept only if it does not regress -> log everything.

Distrust built in:
* retrieval fixes are chosen by an offline grid search that measures source-recall on ALL dev
  questions (not just the failures), so a fix cannot trade one miss for two;
* prompt patches are rejected if they leak eval answers (key facts) into the prompt -
  the optimizer is not allowed to teach to the test;
* a patch that lowers the dev score is reverted, and the revert is logged;
* the holdout split is never shown to the optimizer.
"""
from __future__ import annotations

import copy
import difflib
import json
from collections import Counter
from typing import Callable

from . import llm
from .docs import chunk_documents
from .evaluate import run_eval
from .generator import SECTIONS, TITLES, assemble, lint_sections, parse_sections
from .judge import Judge
from .retrieval import Index
from .runtime import Agent
from .textutil import norm

SECTION_FOR = {
    "wrong_refusal": ["refusal_policy", "grounding_rules"],
    "hallucination": ["grounding_rules", "refusal_policy"],
    "prompt_defect": ["answer_style", "tool_use"],
}
DIAGNOSIS = {
    "wrong_refusal": "The assistant refused questions whose answers WERE present in the retrieved passages. It is over-cautious: it should answer when the passages contain the information, even if phrased differently from the question, and refuse only when they do not.",
    "hallucination": "The assistant stated things not supported by the passages, or answered questions that are out of scope instead of refusing.",
    "prompt_defect": "The right passages were retrieved and the assistant answered, but the answer missed required facts, omitted citations, ignored an available tool, or broke the output format.",
}


def _diff(a: str, b: str) -> str:
    return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), "before", "after", lineterm="", n=1))


# --------------------------------------------------------------------------- retrieval fix
def source_recall(index: Index, cases: list[dict], top_k: int, mode: str) -> tuple[float, list[str]]:
    hits, missed = 0, []
    for c in cases:
        docs = {ch.doc for ch, _ in index.search(c["question"], top_k, mode)}
        exp = set(c["expected_sources"])
        ok = exp <= docs if c["type"] == "multi_doc" else bool(exp & docs)
        hits += ok
        if not ok:
            missed.append(c["id"])
    return (hits / len(cases) if cases else 1.0), missed


def fix_retrieval(defn: dict, agent: Agent, dev_cases: list[dict], failing: list[dict], log: Callable) -> dict | None:
    r = defn["retrieval"]
    ans = [c for c in dev_cases if c["expected_behavior"] == "answer" and c.get("expected_sources")]
    base_recall, base_missed = source_recall(agent.index, ans, int(r["top_k"]), r["mode"])
    modes = ["bm25", "hybrid"] if agent.index.dense_available else ["bm25"]
    sizes = sorted({int(r["chunk_size"]), max(100, int(int(r["chunk_size"]) * 0.6)), min(450, int(int(r["chunk_size"]) * 1.5))})
    trials = []
    for size in sizes:
        idx = agent.index if size == int(r["chunk_size"]) else Index(chunk_documents(agent.docs, r["strategy"], size, size // 6), use_dense=agent.index.dense_available)
        for mode in modes:
            for k in sorted({int(r["top_k"]), min(10, int(r["top_k"]) + 2), min(12, int(r["top_k"]) + 4)}):
                rec, missed = source_recall(idx, ans, k, mode)
                # prefer recall, then smaller k (cheaper prompts), then fewer changes
                trials.append({"chunk_size": size, "mode": mode, "top_k": k, "recall": round(rec, 3), "missed": missed,
                               "cost": (k, size != int(r["chunk_size"]), mode != r["mode"])})
    trials.sort(key=lambda t: (-t["recall"], t["cost"]))
    best = trials[0]
    log(f"    retrieval grid: {len(trials)} configs; current recall {base_recall:.0%} -> best {best['recall']:.0%} "
        f"(k={best['top_k']}, mode={best['mode']}, chunk={best['chunk_size']})")
    new = copy.deepcopy(defn)
    if best["recall"] > base_recall + 1e-9:
        new["retrieval"].update(top_k=best["top_k"], mode=best["mode"], chunk_size=best["chunk_size"], chunk_overlap=best["chunk_size"] // 6)
        ch = [f"{k} {r[k]}->{best[k]}" for k in ("top_k", "mode", "chunk_size") if str(r[k]) != str(best[k])]
        what = "retrieval: " + ", ".join(ch)
    elif not r.get("query_rewrite"):
        new["retrieval"]["query_rewrite"] = True
        what = "retrieval: enabled LLM query rewriting (grid search found no static config with better recall)"
    else:
        return None
    return {"definition": new, "target": "retrieval", "what_changed": what,
            "evidence": {"recall_before": round(base_recall, 3), "recall_after_offline": best["recall"], "missed_before": base_missed,
                         "grid_top5": [{k: v for k, v in t.items() if k != "cost"} for t in trials[:5]]},
            "diff": _diff(json.dumps(r, indent=1), json.dumps(new["retrieval"], indent=1))}


# --------------------------------------------------------------------------- prompt fix
def _leaks(text: str, dev_cases: list[dict]) -> list[str]:
    t = norm(text)
    leaked = []
    for c in dev_cases:
        for f in c.get("key_facts", []):
            nf = norm(f)
            if len(nf) >= 12 and nf in t:
                leaked.append(f)
    return leaked


def fix_prompt(defn: dict, req: dict, category: str, failing: list[dict], dev_cases: list[dict], tried: set, log: Callable) -> dict | None:
    sections = parse_sections(defn["system_prompt"])
    if set(sections) != set(SECTIONS):
        sections = {k: sections.get(k, "") for k in SECTIONS}
    section = next((s for s in SECTION_FOR[category] if (category, s) not in tried), None)
    if category == "prompt_defect" and any("expected tool" in f.get("reason", "") for f in failing) and (category, "tool_use") not in tried:
        section = "tool_use"
    if not section:
        return None
    tried.add((category, section))
    ex = "\n".join(
        f"- Q: {f['question']}\n  A: {f['answer'][:300]}\n  judge: {f['reason'][:250]}" for f in failing[:4])
    others = "\n\n".join(f"## {TITLES[k]}\n{v}" for k, v in sections.items() if k != section)
    for attempt in range(2):
        try:
            out = llm.chat_json(llm.render("prompt_patch", section=TITLES[section], current=sections[section], others=others[:3000],
                                           category=category, diagnosis=DIAGNOSIS[category], examples=ex),
                                validate=llm.require_keys("new_text"), temperature=0.3 + 0.2 * attempt, max_tokens=700)
        except Exception as e:
            log(f"    ! patch generation failed: {e}")
            return None
        new_text = out["new_text"] if isinstance(out["new_text"], str) else "\n".join(f"- {x}" for x in out["new_text"])
        leaked = _leaks(new_text, dev_cases)
        if leaked:
            log(f"    ! patch rejected: leaks eval answers into the prompt {leaked[:2]} (anti-overfitting guard)")
            continue
        new_secs = dict(sections)
        new_secs[section] = new_text.strip()
        tool_names = [t["name"] for t in defn.get("tools", [])]
        new_secs, lint = lint_sections(new_secs, req, tool_names)
        new = copy.deepcopy(defn)
        new["system_prompt"] = assemble(new_secs)
        if category == "hallucination":
            new.setdefault("generation", {})["temperature"] = 0.0
        return {"definition": new, "target": f"prompt:{section}", "what_changed": out.get("change_summary", f"rewrote {section}"),
                "evidence": {"lint_fixes": lint}, "diff": _diff(defn["system_prompt"], new["system_prompt"])}
    return None


# --------------------------------------------------------------------------- loop
def optimize(defn: dict, base_dir, req: dict, dev_cases: list[dict], judge: Judge, start: dict, max_iters: int = 3,
             log: Callable = print, on_iter: Callable | None = None) -> tuple[dict, list[dict]]:
    """`start` = eval result of `defn` on dev (from the tournament). Returns (best_definition, iteration_log)."""
    history = [{"iteration": 0, "version": defn.get("version", 0), "scores": start["scores"], "fixes": [], "accepted": True,
                "note": "baseline (tournament winner)", "results": start["results"]}]
    cur_def, cur = defn, start
    tried: set = set()
    stalls = 0
    for it in range(1, max_iters + 1):
        failing = [r for r in cur["results"] if not r["passed"]]
        if not failing:
            history[-1]["stop_reason"] = "all dev cases pass"
            log("  all dev cases pass - stopping")
            break
        if llm.BUDGET.remaining_fraction() < 0.15:
            history[-1]["stop_reason"] = "budget nearly exhausted"
            log("  budget nearly exhausted - stopping")
            break
        cats = Counter(r["category"] for r in failing)
        log(f"\n  Iteration {it}: {len(failing)} failures {dict(cats)}")
        agent = Agent(cur_def, base_dir=base_dir)
        cand, fixes = cur_def, []
        for cat, _ in cats.most_common():
            if len(fixes) >= 2:
                break
            fl = [r for r in failing if r["category"] == cat]
            if cat == "retrieval_miss":
                if ("retrieval_miss", "grid") in tried:
                    continue
                tried.add(("retrieval_miss", "grid"))
                fx = fix_retrieval(cand, agent, dev_cases, fl, log)
            else:
                fx = fix_prompt(cand, req, cat, fl, dev_cases, tried, log)
            if fx:
                fx.update(category=cat, addresses=[r["id"] for r in fl], why=DIAGNOSIS.get(cat, "Expected sources were not retrieved."))
                cand = fx.pop("definition")
                fixes.append(fx)
                log(f"    fix [{cat} -> {fx['target']}]: {fx['what_changed']}")
        if not fixes:
            history[-1]["stop_reason"] = "no untried targeted fix left"
            log("  no untried targeted fix left - stopping")
            break
        cand = copy.deepcopy(cand)
        cand["version"] = max(h["version"] for h in history) + 1
        new = run_eval(Agent(cand, base_dir=base_dir), dev_cases, judge, log, label=f"iter {it} (v{cand['version']})")
        before, after = cur["scores"]["passed"], new["scores"]["passed"]
        prev_pass = {r["id"] for r in cur["results"] if r["passed"]}
        now_pass = {r["id"] for r in new["results"] if r["passed"]}
        fact_new = new["scores"]["mean_fact_score"] or 0
        fact_old = cur["scores"]["mean_fact_score"] or 0
        accepted = after > before or (after == before and fact_new >= fact_old)
        for fx in fixes:
            fx["fixed_cases"] = sorted(set(fx["addresses"]) & now_pass)
        entry = {"iteration": it, "version": cand["version"], "fixes": fixes, "score_before": cur["scores"]["pass_rate"],
                 "score_after": new["scores"]["pass_rate"], "scores": new["scores"], "accepted": accepted,
                 "newly_passing": sorted(now_pass - prev_pass), "newly_failing": sorted(prev_pass - now_pass), "results": new["results"]}
        if accepted:
            log(f"    ACCEPTED: {before} -> {after} passing (fixed {sorted(now_pass - prev_pass)}, broke {sorted(prev_pass - now_pass)})")
            cur_def, cur = cand, new
            stalls = stalls + 1 if after == before else 0
        else:
            entry["note"] = "REVERTED: fix lowered the dev score"
            log(f"    REVERTED: {before} -> {after} passing (broke {sorted(prev_pass - now_pass)})")
            stalls += 1
        history.append(entry)
        if on_iter:
            on_iter(entry)
        if stalls >= 2:
            entry["stop_reason"] = "early stop: two iterations without improvement (budget guard)"
            log("  early stop: two iterations without improvement")
            break
    return cur_def, history
