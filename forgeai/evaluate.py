"""Runs an agent over an eval set and scores it."""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .judge import Judge
from .runtime import Agent

WORKERS = int(os.environ.get("FORGE_WORKERS", "2"))


def run_eval(agent: Agent, cases: list[dict], judge: Judge, log: Callable = print, label: str = "") -> dict:
    def one(case):
        try:
            resp = agent.answer(case["question"])
        except Exception as e:
            resp = {"answer": f"[agent error: {e}]", "refused": False, "citations": [], "cited_docs": [], "passages": [],
                    "tool_results": [], "contract_violations": [f"agent crashed: {e}"]}
        v = judge.judge(case, resp)
        v["passages"] = [{"label": p["label"], "doc": p["doc"], "chunk_id": p["chunk_id"]} for p in resp.get("passages", [])]
        v["tool_results"] = resp.get("tool_results", [])
        return v

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(one, cases))
    s = score(results)
    if label:
        log(f"  {label}: pass {s['passed']}/{s['n']} ({s['pass_rate']:.0%}) | answer acc {s['answer_accuracy']} | grounded {s['groundedness']} | refusal recall {s['refusal_recall']} | false refusals {s['false_refusal_rate']}")
    return {"results": results, "scores": s}


def _rate(xs) -> float | None:
    xs = list(xs)
    return round(sum(xs) / len(xs), 3) if xs else None


def score(results: list[dict]) -> dict:
    n = len(results)
    ans = [r for r in results if r["expected_behavior"] == "answer"]
    ref = [r for r in results if r["expected_behavior"] == "refuse"]
    answered = [r for r in ans if not r["refused"]]
    by_type = defaultdict(lambda: [0, 0])
    for r in results:
        by_type[r["type"]][1] += 1
        by_type[r["type"]][0] += int(r["passed"])
    return {
        "n": n,
        "passed": sum(r["passed"] for r in results),
        "pass_rate": round(sum(r["passed"] for r in results) / n, 3) if n else 0.0,
        "answer_accuracy": _rate(r["correct"] for r in ans),
        "groundedness": _rate(bool(r["grounded"]) for r in answered),
        "refusal_recall": _rate(r["refused"] for r in ref),
        "false_refusal_rate": _rate(r["refused"] for r in ans),
        "retrieval_hit_rate": _rate(r.get("retrieval_hit", False) for r in ans),
        "contract_violation_rate": _rate(bool(r["contract_violations"]) for r in results),
        "mean_fact_score": _rate(r["fact_score"] for r in ans if r["fact_score"] is not None),
        "judge_disagreements": sum(r.get("judge_disagreements", 0) for r in results),
        "judge_flags_overruled": sum(len(r.get("judge_flags_overruled", [])) for r in results),
        "by_type": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_type.items())},
        "failure_categories": dict(Counter(r["category"] for r in results if not r["passed"])),
        "mean_latency_s": _rate(r.get("latency_s") or 0 for r in results),
    }
