"""The factory, end to end. Every stage writes its artifact to the run folder so a reviewer
can audit (and re-run) any step."""
from __future__ import annotations

import copy
import json
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

from . import llm
from .config import SETTINGS
from .docs import chunk_documents, load_folder
from .evalgen import generate_evalset
from .evaluate import run_eval
from .generator import build_definition, prompt_candidates, retrieval_params, select_tools
from .guard import apply_guard, run_guard
from .intake import build_inventory, human_checkpoint, interview, requirements_markdown, write_requirements
from .judge import Judge
from .optimizer import optimize
from .report import write_report
from .retrieval import Index
from .runtime import Agent


def _w(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False, default=str))


def build(brief: str, docs_dir: str | Path, out_dir: str | Path, answers: Optional[dict] = None, interactive: bool = False,
          max_iters: int = 3, n_candidates: int = 3, max_tokens: int = 3_000_000, max_minutes: float = 180,
          log: Callable = print, eval_targets: Optional[dict] = None, requirements_override: Optional[dict] = None) -> dict:
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    budget = llm.Budget(max_tokens=max_tokens, max_seconds=max_minutes * 60)
    llm.set_budget(budget)
    # self-contained run: copy the knowledge folder next to the agent definition
    kdir = out / "knowledge"
    if kdir.exists():
        shutil.rmtree(kdir)
    shutil.copytree(docs_dir, kdir, ignore=shutil.ignore_patterns(".*"))
    _w(out / "brief.md", brief)
    log(f"ForgeAI | model={SETTINGS.model} judge={SETTINGS.judge_model} | out={out}")

    # 1. intake -------------------------------------------------------------------
    docs = load_folder(kdir)
    if not docs:
        raise SystemExit(f"No readable documents in {docs_dir}")
    log(f"\n[1/8] Intake: {len(docs)} documents")
    with llm.stage("intake"):
        inventory = build_inventory(docs, log)
        _w(out / "01_inventory.json", inventory)
        clar = interview(brief, inventory, answers=answers, interactive=interactive, log=log)
        _w(out / "02_clarifications.json", clar)
        if requirements_override:
            req = dict(requirements_override)
            req.setdefault("brief", brief)
            req.setdefault("clarifications", clar)
            req.setdefault("capabilities_needed", [])
            req["approval"] = {"status": "approved/edited by requester in UI", "edited": True}
        else:
            req = write_requirements(brief, inventory, clar)

    # 2. groundability guard ------------------------------------------------------
    log("\n[2/8] Groundability guard")
    guard_index = Index(chunk_documents(docs, "section", 220, 40))
    with llm.stage("guard"):
        g = run_guard(req, guard_index, [d.name for d in docs], log)
        req = apply_guard(req, g)
    if g["warnings"]:
        log(f"  ⚠ {len(g['warnings'])} groundability warning(s): status={g['status']}")
    if not requirements_override:
        req = human_checkpoint(req, out, interactive, log)
    if req.pop("_needs_recheck", False):
        with llm.stage("guard"):
            req = apply_guard(req, run_guard(req, guard_index, [d.name for d in docs], log))
    _w(out / "03_requirements.json", req)
    _w(out / "03_requirements.md", requirements_markdown(req))

    # 3. generator ----------------------------------------------------------------
    log("\n[3/8] Agent generator")
    with llm.stage("generator"):
        attached, rejected = select_tools(req, docs, log)
        retr = retrieval_params(docs)
        log(f"  retrieval: {retr['rationale']}")
        cands = prompt_candidates(req, [t["name"] for t in attached], n=n_candidates, log=log)
    if not cands:
        raise RuntimeError("no system prompt candidate could be generated")
    _w(out / "04_prompt_candidates.json", cands)

    # 4. eval generator -------------------------------------------------------------
    log("\n[4/8] Eval generator")
    chunks = chunk_documents(docs, retr["strategy"], retr["chunk_size"], retr["chunk_overlap"])
    with llm.stage("evalgen"):
        ev = generate_evalset(docs, chunks, Index(chunks), req, inventory, [t["name"] for t in attached], log, targets=eval_targets)
    _w(out / "05_evalset.json", ev)
    dev = [c for c in ev["cases"] if c["split"] == "dev"]
    hold = [c for c in ev["cases"] if c["split"] == "holdout"]
    log(f"  {len(ev['cases'])} cases {ev['counts']} | dev={len(dev)} holdout={len(hold)} | audit {ev['audit']['summary']}")

    # 5. judge calibration ----------------------------------------------------------
    log("\n[5/8] Judge calibration (planted canaries)")
    judge = Judge()
    with llm.stage("judge_calibration"):
        cal = judge.calibrate(ev["cases"])
    _w(out / "06_judge_calibration.json", cal)
    log(f"  LLM judge acc {cal['llm_judge_accuracy']} | verbosity trap {cal['llm_verbosity_trap_accuracy']} | position consistency {cal['position_consistency']} -> mode={cal['llm_mode']}")

    # 6. prompt tournament ------------------------------------------------------------
    log(f"\n[6/8] Prompt tournament ({len(cands)} candidates on dev split)")
    tour = {"candidates": [], "winner": None}
    evaluated = []
    with llm.stage("tournament"):
        for c in cands:
            d = build_definition(req, docs, "knowledge", attached, rejected, c, retr)
            r = run_eval(Agent(d, base_dir=out), dev, judge, log, label=f"candidate {c['id']}")
            evaluated.append((c, d, r))
            tour["candidates"].append({"id": c["id"], "style": c["style"], "lint_fixes": c["lint_fixes"], **{k: r["scores"][k] for k in ("passed", "n", "pass_rate", "mean_fact_score")}})
        evaluated.sort(key=lambda x: (-x[2]["scores"]["passed"], -(x[2]["scores"]["mean_fact_score"] or 0)))
        if len(evaluated) > 1 and evaluated[0][2]["scores"]["passed"] == evaluated[1][2]["scores"]["passed"]:
            # tie -> position-debiased pairwise judge on answerable dev cases
            a, b = evaluated[0], evaluated[1]
            wins = {"A": 0, "B": 0, "tie": 0}
            ra = {x["id"]: x for x in a[2]["results"]}
            rb = {x["id"]: x for x in b[2]["results"]}
            for case in [c for c in dev if c["expected_behavior"] == "answer"][:6]:
                wins[judge.pairwise(case["question"], case["key_facts"], ra[case["id"]]["answer"], rb[case["id"]]["answer"])] += 1
            if wins["B"] > wins["A"]:
                evaluated[0], evaluated[1] = b, a
            tour["tiebreak"] = f"{a[0]['id']} vs {b[0]['id']}: {wins} (each pair judged in both orders; inconsistent verdicts count as tie)"
    win_c, v0, v0_res = evaluated[0]
    tour["winner"] = win_c["id"]
    _w(out / "07_tournament.json", tour)
    _w(out / "agent_v0.json", v0)
    log(f"  winner: {win_c['id']}")

    # 7. critic-optimizer loop ------------------------------------------------------------
    log(f"\n[7/8] Critic-optimizer loop (max {max_iters} iterations)")
    iters_dir = out / "iterations"

    def save_iter(e):
        _w(iters_dir / f"iter_{e['iteration']}.json", e)

    _w(iters_dir / "iter_0.json", {"iteration": 0, "scores": v0_res["scores"], "results": v0_res["results"]})
    with llm.stage("optimizer"):
        final, hist = optimize(v0, out, req, dev, judge, v0_res, max_iters=max_iters, log=log, on_iter=save_iter)
    _w(out / "agent.json", final)
    _w(out / "08_iteration_log.json", [{k: v for k, v in h.items() if k != "results"} for h in hist])

    # 8. holdout + full eval + report --------------------------------------------------------
    log("\n[8/8] Holdout check & report")
    holdout = {}
    with llm.stage("final_eval"):
        if hold:
            holdout["v0"] = run_eval(Agent(v0, base_dir=out), hold, judge, log, label="holdout v0")
            holdout["final"] = run_eval(Agent(final, base_dir=out), hold, judge, log, label=f"holdout v{final['version']}") if final["version"] != v0["version"] else holdout["v0"]
        best_dev = next(h for h in reversed(hist) if h["accepted"])
        final_all = {"results": best_dev["results"] + (holdout["final"]["results"] if hold else [])}
        from .evaluate import score
        final_all["scores"] = score(final_all["results"])
    _w(out / "09_holdout.json", {k: {"scores": v["scores"], "results": v["results"]} for k, v in holdout.items()})
    scorecard = {"agent": final["name"], "final_version": final["version"], "overall": final_all["scores"],
                 "dev_by_iteration": [{"iteration": h["iteration"], "version": h["version"], "accepted": h["accepted"], **h["scores"]} for h in hist],
                 "holdout": {k: v["scores"] for k, v in holdout.items()}, "judge_mode": cal["llm_mode"]}
    _w(out / "scorecard.json", scorecard)
    _w(out / "final_results.json", final_all["results"])
    budget_d = llm.BUDGET.to_dict()
    _w(out / "budget.json", budget_d)
    with llm.stage("report"):
        run = {"requirements": req, "agent": final, "evalset": ev, "history": hist, "holdout": holdout, "calibration": cal,
               "tournament": tour, "budget": budget_d, "final_all": final_all, "out_dir": out}
        md = write_report(run, log)
    _w(out / "REPORT.md", md)
    _w(out / "final_results.json", final_all["results"])  # now includes the failure adjudication
    s = final_all["scores"]
    log(f"\nDone in {(time.time()-t0)/60:.1f} min. Final: {s['passed']}/{s['n']} ({s['pass_rate']:.0%}). Report: {out/'REPORT.md'}")
    return {"scorecard": scorecard, "out": str(out)}
