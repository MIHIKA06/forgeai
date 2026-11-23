"""Stage 7 - honest reporting."""
from __future__ import annotations

import json
from typing import Callable

from . import llm


def _pct(x) -> str:
    return "–" if x is None else f"{x:.0%}"


def evidence(r: dict) -> str:
    """Deterministic root-cause evidence for one failure (no LLM)."""
    if r["expected_behavior"] == "refuse":
        return f"answered instead of refusing; it cited {r['cited_docs'] or 'nothing'} - retrieved passages on a related topic ({', '.join(r['retrieved_docs'][:3])}) were treated as an answer"
    if r["category"] == "retrieval_miss":
        return f"expected source not in top-k: retrieved {r['retrieved_docs']}"
    if r["category"] == "wrong_refusal":
        return f"source WAS retrieved ({r['retrieved_docs']}) but the model refused"
    bits = []
    if r.get("ungrounded_numbers"):
        bits.append(f"numbers absent from every passage: {r['ungrounded_numbers']}")
    if r.get("llm_unsupported"):
        bits.append(f"judge-flagged claims: {r['llm_unsupported'][:1]}")
    if r.get("fact_score") is not None:
        bits.append(f"fact score {r['fact_score']}")
    if not r.get("cited_expected", True):
        bits.append("expected source not cited")
    if r.get("contract_violations"):
        bits.append(f"contract: {r['contract_violations'][:1]}")
    return "; ".join(bits)


def explain_failures(failures: list[dict], history: list[dict]) -> dict:
    if not failures:
        return {"summary": "No remaining failures on this split. Treat this with suspicion: the eval set is auto-generated and may be too easy - see the eval audit and holdout results.", "per_case": []}
    ftxt = "\n".join(f"- {f['id']} ({f['type']}, {f['category']}): Q: {f['question']} | A: {f['answer'][:220]} | judge: {f['reason'][:220]} | evidence: {evidence(f)}"
                     for f in failures[:14])
    fixes = "\n".join(f"- iter {h['iteration']}: {fx['category']} -> {fx['target']}: {fx['what_changed']} ({'accepted' if h['accepted'] else 'reverted'})"
                      for h in history for fx in h.get("fixes", [])) or "(none)"
    try:
        return llm.chat_json(llm.render("failure_explain", failures=ftxt, fixes=fixes), validate=llm.require_keys("summary"), max_tokens=1200)
    except Exception as e:
        return {"summary": f"(automatic explanation failed: {e})", "per_case": []}


def scorecard_table(history: list[dict]) -> str:
    rows = ["| Iter | Agent ver | Dev pass | Answer acc | Grounded | Refusal recall | False refusals | Retrieval hit | Failure categories | Outcome |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for h in history:
        s = h["scores"]
        cats = ", ".join(f"{k}:{v}" for k, v in s["failure_categories"].items()) or "–"
        outcome = "baseline" if h["iteration"] == 0 else ("accepted" if h["accepted"] else "**reverted**")
        rows.append(f"| {h['iteration']} | v{h['version']} | {s['passed']}/{s['n']} ({_pct(s['pass_rate'])}) | {_pct(s['answer_accuracy'])} | {_pct(s['groundedness'])} | "
                    f"{_pct(s['refusal_recall'])} | {_pct(s['false_refusal_rate'])} | {_pct(s['retrieval_hit_rate'])} | {cats} | {outcome} |")
    return "\n".join(rows)


def write_report(run: dict, log: Callable = print) -> str:
    req, defn, ev, hist, hold = run["requirements"], run["agent"], run["evalset"], run["history"], run["holdout"]
    cal, tour, budget = run["calibration"], run["tournament"], run["budget"]
    final_dev = hist[-1]["scores"] if hist[-1]["accepted"] else next(h for h in reversed(hist) if h["accepted"])["scores"]
    v0_dev = hist[0]["scores"]
    hv0, hfin = hold.get("v0", {}).get("scores"), hold.get("final", {}).get("scores")
    all_final = run["final_all"]["scores"]
    remaining = [r for r in run["final_all"]["results"] if not r["passed"]]
    expl = explain_failures(remaining, hist)
    why = {p.get("id"): p.get("why", "") for p in expl.get("per_case", []) if isinstance(p, dict)}

    L = [f"# ForgeAI quality report — `{defn['name']}`", ""]
    L += [f"> **Final agent v{defn['version']}: {all_final['passed']}/{all_final['n']} eval cases pass ({_pct(all_final['pass_rate'])}).** "
          f"Dev split {_pct(v0_dev['pass_rate'])} → {_pct(final_dev['pass_rate'])} over {len(hist)-1} optimisation iteration(s); "
          + (f"untouched holdout split {_pct(hv0['pass_rate'])} → {_pct(hfin['pass_rate'])}." if hv0 and hfin else "no holdout split.")]
    if hv0 and hfin:
        dev_gain = final_dev["pass_rate"] - v0_dev["pass_rate"]
        hold_gain = hfin["pass_rate"] - hv0["pass_rate"]
        if dev_gain - hold_gain > 0.15:
            L.append(f"> ⚠️ **Possible overfitting:** dev improved by {dev_gain:+.0%} but holdout only by {hold_gain:+.0%}. Treat the dev number as optimistic.")
    if all_final["pass_rate"] >= 0.98:
        L.append("> ⚠️ A ~100% score on an auto-generated eval set is more likely a sign the tests are too easy than that the agent is perfect. Check the eval audit below.")
    L += ["", "## What still fails and why", "", expl.get("summary", ""), ""]
    if remaining:
        L += ["| Case | Type | Split | Category | Judge verdict | Deterministic evidence | LLM root-cause hypothesis |", "|---|---|---|---|---|---|---|"]
        for r in remaining:
            L.append(f"| {r['id']} | {r['type']} | {r['split']} | {r['category']} | {r['reason'][:120].replace('|', '/')} | {evidence(r)[:160].replace('|', '/')} | {why.get(r['id'], '').replace('|', '/')} |")
        L += ["", "<details><summary>Questions and answers of the failing cases</summary>", ""]
        for r in remaining:
            L.append(f"- **{r['id']}** Q: {r['question']}  \n  A: {r['answer'][:400]}")
        L += ["", "</details>"]
    L += ["", "## Per-iteration scorecard (dev split — the only split the optimiser sees)", "", scorecard_table(hist), ""]
    if hv0 and hfin:
        L += ["## Generalisation check (holdout split — never shown to the optimiser)", "",
              "| Agent | Holdout pass | Answer acc | Grounded | Refusal recall | False refusals |", "|---|---|---|---|---|---|"]
        for name, s in (("v0 (before loop)", hv0), (f"v{defn['version']} (final)", hfin)):
            L.append(f"| {name} | {s['passed']}/{s['n']} ({_pct(s['pass_rate'])}) | {_pct(s['answer_accuracy'])} | {_pct(s['groundedness'])} | {_pct(s['refusal_recall'])} | {_pct(s['false_refusal_rate'])} |")
        L.append("")
    L += ["## Change log", ""]
    for h in hist[1:]:
        L.append(f"### Iteration {h['iteration']} — {'accepted' if h['accepted'] else 'REVERTED'} (dev {_pct(h['score_before'])} → {_pct(h['score_after'])})")
        L.append(f"Newly passing: {h['newly_passing'] or '–'} · Newly failing: {h['newly_failing'] or '–'}")
        for fx in h["fixes"]:
            L += ["", f"- **{fx['category']} → `{fx['target']}`**: {fx['what_changed']}", f"  - Why: {fx['why']}",
                  f"  - Addressed failures: {fx['addresses']} · actually fixed: {fx.get('fixed_cases', [])}"]
            if fx.get("evidence", {}).get("recall_before") is not None:
                e = fx["evidence"]
                L.append(f"  - Offline retrieval check: source recall {_pct(e['recall_before'])} → {_pct(e['recall_after_offline'])}")
            L += ["", "<details><summary>diff</summary>", "", "```diff", fx["diff"][:4000], "```", "</details>"]
        if h.get("stop_reason"):
            L.append(f"\n_Stopped: {h['stop_reason']}_")
        L.append("")
    if hist[-1].get("stop_reason") or hist[0].get("stop_reason"):
        L.append(f"_Loop stop reason: {hist[-1].get('stop_reason') or hist[0].get('stop_reason')}_\n")

    L += ["## Requirements & groundability guard", "", f"- **Purpose:** {req['purpose']}", f"- **Audience:** {req['audience']}",
          f"- **Approval:** {req.get('approval', {}).get('status', '–')}", f"- **Guard status:** `{req['groundability']['status']}` "
          f"(topic coverage {_pct(req['groundability']['coverage'])})"]
    for w in req["groundability"]["warnings"]:
        L.append(f"  - ⚠️ {w}")
    L += ["", "## Tool selection", "", "| Tool | Decision | Reason |", "|---|---|---|"]
    for t in defn["tools"]:
        L.append(f"| {t['name']} | ✅ attached | {t['justification']} |")
    for t in defn.get("tools_rejected", []):
        L.append(f"| {t['name']} | ❌ rejected | {t['reason']} |")
    L += ["", "## Prompt tournament", "", "| Candidate | Dev pass | Mean fact score | Lint fixes | Result |", "|---|---|---|---|---|"]
    for c in tour["candidates"]:
        L.append(f"| {c['id']} | {c['passed']}/{c['n']} | {c['mean_fact_score']} | {len(c['lint_fixes'])} | {'🏆 winner' if c['id'] == tour['winner'] else ''} |")
    if tour.get("tiebreak"):
        L.append(f"\nTie-break (position-debiased pairwise judge): {tour['tiebreak']}")
    L += ["", "## Eval set", "", f"{len(ev['cases'])} generated cases: {ev['counts']} · splits {ev['splits']}.",
          f"Generation audit (claims checked deterministically): {ev['audit']['summary'] or 'no drops'}.", ""]
    L += ["## Judge calibration (planted canaries)", "",
          f"- Judge model `{cal['judge_model']}` vs agent model `{cal['agent_model']}` → self-preference guard: {cal['self_preference_guard']}",
          f"- LLM judge accuracy on {cal['n_canaries']} canaries: {_pct(cal['llm_judge_accuracy'])} · deterministic checker: {_pct(cal['deterministic_accuracy'])}",
          f"- Verbosity trap (long, fluent, wrong answers) caught: {_pct(cal['llm_verbosity_trap_accuracy'])} · false-accept rate on corrupted answers: {_pct(cal['llm_false_accept_rate_on_corrupted'])}",
          f"- Position consistency (fact order reversed): {_pct(cal['position_consistency'])}",
          f"- Resulting judge mode: **{cal['llm_mode']}** — {cal['policy']}",
          f"- Judge/deterministic disagreements during final eval: {all_final['judge_disagreements']}",
          f"- 'Unsupported claim' flags raised by the LLM judge but **overruled** because the claim is found verbatim-ish in the passages/question: {all_final.get('judge_flags_overruled', 0)} "
          "(observed failure mode of the 8B judge: it flags sentences copied from the passages; its groundedness veto is therefore only accepted when the deterministic checker agrees)", ""]
    L += ["## Final agent definition", "", f"- Retrieval: `{json.dumps({k: v for k, v in defn['retrieval'].items() if k != 'rationale'})}`",
          f"- Output contract: JSON `{{answer, citations, refused}}`, max {defn['output_contract']['max_words']} words, citations required",
          f"- Prompt candidate: {defn.get('prompt_candidate')}", "", "<details><summary>System prompt</summary>", "", "```", defn["system_prompt"], "```", "</details>", ""]
    L += ["## Budget", "", f"- Tokens: {budget['tokens_total']:,} of {budget['max_tokens']:,} · LLM calls: {budget['calls']} (cache hits {budget['cache_hits']}) · wall time {budget['wall_seconds']/60:.1f} min", "",
          "| Stage | Calls | Tokens | LLM seconds |", "|---|---|---|---|"]
    for k, v in budget["by_stage"].items():
        L.append(f"| {k} | {v['calls']} | {v['tokens']:,} | {v['seconds']} |")
    L += ["", "## Known limitations of this report", "",
          "- The eval set is generated by the same family of small model that builds the agent; it inherits that model's blind spots. Key facts are verified to exist in the source, but question *quality* is not.",
          "- Fact matching is lexical + LLM; correct answers phrased very differently can be scored as misses (see judge disagreements).",
          "- Out-of-scope 'adjacent' questions are verified unanswerable by a second model, which can itself be wrong.",
          "- Scores come from a single run at near-zero temperature; small differences (±1 case) are within noise.", ""]
    return "\n".join(L)
