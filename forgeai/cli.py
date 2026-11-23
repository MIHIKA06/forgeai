"""ForgeAI command line.

  python -m forgeai build    --brief brief.md --docs ./docs --out runs/x [--interactive] [--answers a.json]
  python -m forgeai chat     --agent runs/x/agent.json
  python -m forgeai eval     --agent some_agent.json --evalset runs/x/05_evalset.json
  python -m forgeai regress  --run runs/x --docs ./docs_v2 [--rebuild]
  python -m forgeai baseline --run runs/x --agent baselines/human_agent.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def _load_brief(s: str) -> str:
    p = Path(s)
    return p.read_text().strip() if p.exists() else s


def cmd_build(a):
    from .pipeline import build

    answers = json.loads(Path(a.answers).read_text()) if a.answers else None
    build(_load_brief(a.brief), a.docs, a.out, answers=answers, interactive=a.interactive, max_iters=a.max_iters,
          n_candidates=a.candidates, max_tokens=a.budget_tokens, max_minutes=a.budget_minutes)


def cmd_chat(a):
    from .runtime import Agent

    agent = Agent.load(a.agent)
    d = agent.d
    print(f"\n== {d['name']} v{d.get('version', 0)} ==\n{d.get('description', '')}")
    print(f"tools: {[t['name'] for t in d.get('tools', [])] or 'none'} | knowledge: {len(agent.docs)} files, {len(agent.chunks)} chunks")
    print("type 'exit' to quit, ':debug' to toggle retrieval trace\n")
    history, debug = [], False
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q in ("exit", "quit"):
            break
        if q == ":debug":
            debug = not debug
            continue
        r = agent.answer(q, history)
        tag = " [REFUSED]" if r["refused"] else ""
        print(f"\nagent{tag}> {r['answer']}")
        if r["citations"]:
            srcs = {p["label"]: f"{p['doc']}" + (f" > {p['section']}" if p["section"] else "") for p in r["passages"]}
            srcs.update({t["label"]: f"tool {t['tool']}({t['args']})" for t in r["tool_results"]})
            for c in r["citations"]:
                print(f"   [{c}] {srcs.get(c, '?')}")
        for t in r["tool_results"]:
            print(f"   tool {t['tool']} {t['args']} -> {json.dumps(t['result'])[:200]}")
        if r["contract_violations"]:
            print(f"   (contract warnings: {r['contract_violations']})")
        if debug:
            for p in r["passages"]:
                print(f"   ~ {p['label']} {p['chunk_id']} score={p['score']}")
        print(f"   ({r['latency_s']}s)\n")
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": r["answer"]}]


def cmd_eval(a):
    from .evaluate import run_eval
    from .judge import Judge
    from .runtime import Agent

    ev = json.loads(Path(a.evalset).read_text())
    cases = [c for c in ev["cases"] if a.split == "all" or c["split"] == a.split]
    r = run_eval(Agent.load(a.agent), cases, Judge(), label=Path(a.agent).name)
    print(json.dumps(r["scores"], indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(r, indent=2, default=str))


def cmd_regress(a):
    """Stretch: documents changed -> re-run the OLD eval set against the regenerated agent."""
    from .docs import load_folder
    from .evaluate import run_eval
    from .judge import Judge
    from .runtime import Agent
    from .textutil import fact_in_text

    run = Path(a.run)
    out = Path(a.out or f"{run}_regression")
    old_eval = json.loads((run / "05_evalset.json").read_text())["cases"]
    old_res = {r["id"]: r for r in json.loads((run / "final_results.json").read_text())}
    if a.rebuild:
        from .pipeline import build

        req = json.loads((run / "03_requirements.json").read_text())
        answers = {str(i + 1): c["answer"] for i, c in enumerate(req.get("clarifications", []))}
        build((run / "brief.md").read_text(), a.docs, out, answers=answers, max_iters=a.max_iters)
        new_def = json.loads((out / "agent.json").read_text())
    else:
        out.mkdir(parents=True, exist_ok=True)
        if (out / "knowledge").exists():
            shutil.rmtree(out / "knowledge")
        shutil.copytree(a.docs, out / "knowledge")
        new_def = json.loads((run / "agent.json").read_text())
        new_def["knowledge"]["docs_path"] = "knowledge"
        new_def["knowledge"]["files"] = sorted(p.name for p in (out / "knowledge").iterdir())
        (out / "agent.json").write_text(json.dumps(new_def, indent=2))
    import re as _re
    from .textutil import norm, similarity
    old_docs = {d.name: d.text for d in load_folder(run / "knowledge")}
    new_docs = {d.name: d.text for d in load_folder(out / "knowledge")}

    def _sentences(t):
        return [x.strip() for x in _re.split(r"(?<=[.!?])\s+|\n+", t) if len(x.split()) >= 3]

    def stale_facts(case):
        """A fact is stale if the sentence that stated it in the OLD version of its source document
        no longer exists in the NEW version (document edited or removed)."""
        bad = []
        for f in case.get("key_facts", []):
            for src in case.get("expected_sources", []):
                if src not in old_docs or old_docs.get(src) == new_docs.get(src):
                    continue
                carriers = [s for s in _sentences(old_docs[src]) if fact_in_text(f, s, 0.85)]
                new_norm = norm(new_docs.get(src, ""))
                # exact (normalised) containment: a fuzzy match would accept '10 days' -> '15 days'
                if not carriers:
                    continue
                # the carrier is the sentence most related to THIS test's question (not any sentence with '10 days')
                best = max(carriers, key=lambda x: similarity(x, case["question"] + " " + " ".join(case.get("key_facts", []))))
                if norm(best) not in new_norm:
                    bad.append(f)
                    break
        return bad

    stale = {c["id"]: stale_facts(c) for c in old_eval if c["expected_behavior"] == "answer"}
    old_eval_by_id = {c["id"]: c for c in old_eval}
    r = run_eval(Agent(new_def, base_dir=out), old_eval, Judge(), label="old evals vs regenerated agent")
    rows, broke, fixed, drift = [], [], [], []
    for v in r["results"]:
        was = old_res.get(v["id"], {}).get("passed")
        st = stale.get(v["id"]) or []
        if st:
            status = "STALE TEST (source facts changed)" if not v["passed"] else "pass (despite changed source)"
            drift.append(v["id"])
        elif was and not v["passed"]:
            srcs = old_eval_by_id[v["id"]].get("expected_sources", [])
            changed = [x for x in srcs if old_docs.get(x) != new_docs.get(x)]
            status = "BROKE (source changed)" if changed else "BROKE (sources unchanged -> model instability, not the doc edit)"
            broke.append(v["id"])
        elif not was and v["passed"]:
            status = "fixed"
            fixed.append(v["id"])
        else:
            status = "pass" if v["passed"] else "still failing"
        rows.append(f"| {v['id']} | {v['type']} | {'pass' if was else 'fail'} | {'pass' if v['passed'] else 'fail'} | {status} | {('; '.join(st))[:80] or v['reason'][:80]} |")
    md = [f"# Regression report: `{run.name}` with changed documents", "",
          f"Old eval set ({len(old_eval)} cases) re-run against the {'rebuilt' if a.rebuild else 're-indexed'} agent.", "",
          f"- **Broke:** {broke or 'none'}", f"- **Fixed:** {fixed or 'none'}",
          f"- **Stale tests** (expected facts no longer in the documents — the test, not the agent, needs updating): {drift or 'none'}",
          "- Note: a case that broke although none of its source documents changed is run-to-run instability of the small model (the retrieved context shifted), not a regression caused by the edit.",
          f"- Score: {sum(1 for x in old_res.values() if x['passed'])}/{len(old_res)} → {r['scores']['passed']}/{r['scores']['n']}", "",
          "| Case | Type | Before | After | Status | Detail |", "|---|---|---|---|---|---|"] + rows
    (out / "REGRESSION.md").write_text("\n".join(md) + "\n")
    (out / "regression.json").write_text(json.dumps({"broke": broke, "fixed": fixed, "stale": drift, "scores": r["scores"], "results": r["results"]}, indent=2, default=str))
    print("\n".join(md[:8]))


def cmd_baseline(a):
    """Stretch: factory vs a hand-written agent on the same eval set and judge."""
    from .evaluate import run_eval
    from .judge import Judge
    from .runtime import Agent

    run = Path(a.run)
    cases = json.loads((run / "05_evalset.json").read_text())["cases"]
    factory = {r["id"]: r for r in json.loads((run / "final_results.json").read_text())}
    hp = Path(a.agent)
    hdef = json.loads(hp.read_text())
    kp = Path(hdef["knowledge"]["docs_path"])
    base_dir = hp.parent
    if not (base_dir / kp).exists():
        hdef["knowledge"]["docs_path"] = str((run / "knowledge").resolve())
    judge = Judge()
    judge.calibrate(cases)
    h = run_eval(Agent(hdef, base_dir=base_dir), cases, judge, label="human baseline")
    hres = {r["id"]: r for r in h["results"]}
    from .evaluate import score

    fs, hs = score(list(factory.values())), h["scores"]
    rows = []
    for c in cases:
        f_ok, h_ok = factory[c["id"]]["passed"], hres[c["id"]]["passed"]
        if f_ok != h_ok:
            rows.append(f"| {c['id']} | {c['type']} | {'✅' if f_ok else '❌'} | {'✅' if h_ok else '❌'} | {(hres[c['id']]['reason'] if not h_ok else factory[c['id']]['reason'])[:110]} |")
    met = ["pass_rate", "answer_accuracy", "groundedness", "refusal_recall", "false_refusal_rate", "contract_violation_rate"]
    md = ["# Factory vs human baseline", "", f"Same {len(cases)} generated eval cases, same judge (mode: {judge.llm_mode}).", "",
          "| Metric | Factory | Human |", "|---|---|---|"] + [f"| {m} | {fs.get(m)} | {hs.get(m)} |" for m in met]
    md += ["", "| By type | Factory | Human |", "|---|---|---|"] + [f"| {t} | {fs['by_type'].get(t)} | {hs['by_type'].get(t)} |" for t in sorted(fs["by_type"])]
    md += ["", "## Cases where they differ", "", "| Case | Type | Factory | Human | Why (loser's judge evidence) |", "|---|---|---|---|---|"] + rows
    out = run / "BASELINE_COMPARISON.md"
    out.write_text("\n".join(md) + "\n")
    (run / "baseline_results.json").write_text(json.dumps(h, indent=2, default=str))
    print("\n".join(md))


def main(argv=None):
    p = argparse.ArgumentParser(prog="forgeai", description="ForgeAI - the agent that builds agents")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="run the factory end to end")
    b.add_argument("--brief", required=True, help="brief text or path to a file containing it")
    b.add_argument("--docs", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--answers", help="JSON {question_number: answer} for scripted clarifications")
    b.add_argument("--interactive", action="store_true", help="ask clarifying questions + requirements approval in the terminal")
    b.add_argument("--max-iters", type=int, default=3)
    b.add_argument("--candidates", type=int, default=3)
    b.add_argument("--budget-tokens", type=int, default=3_000_000)
    b.add_argument("--budget-minutes", type=float, default=180)
    b.set_defaults(fn=cmd_build)
    c = sub.add_parser("chat", help="chat with any generated agent definition")
    c.add_argument("--agent", required=True)
    c.set_defaults(fn=cmd_chat)
    e = sub.add_parser("eval", help="evaluate an agent definition on an eval set")
    e.add_argument("--agent", required=True)
    e.add_argument("--evalset", required=True)
    e.add_argument("--split", default="all", choices=["all", "dev", "holdout"])
    e.add_argument("--out")
    e.set_defaults(fn=cmd_eval)
    r = sub.add_parser("regress", help="documents changed: re-run the old eval set against the regenerated agent")
    r.add_argument("--run", required=True)
    r.add_argument("--docs", required=True)
    r.add_argument("--out")
    r.add_argument("--rebuild", action="store_true", help="re-run the whole factory instead of just re-indexing")
    r.add_argument("--max-iters", type=int, default=3)
    r.set_defaults(fn=cmd_regress)
    bl = sub.add_parser("baseline", help="compare a hand-written agent with the factory's agent")
    bl.add_argument("--run", required=True)
    bl.add_argument("--agent", required=True)
    bl.set_defaults(fn=cmd_baseline)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main(sys.argv[1:])
