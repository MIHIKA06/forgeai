"""ForgeAI web UI: factory wizard (with human checkpoint), run explorer, and generic chat runner.

    streamlit run app.py
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
RUNS = ROOT / "runs"
DEMOS = ROOT / "demos"

st.set_page_config(page_title="ForgeAI — the agent that builds agents", page_icon="🏭", layout="wide")

# Secrets (hosted) -> env, before importing forgeai.config
try:
    for k in ("FORGE_BASE_URL", "FORGE_API_KEY", "FORGE_MODEL", "FORGE_JUDGE_MODEL", "FORGE_EMBED_MODEL"):
        if k in st.secrets and not os.environ.get(k):
            os.environ[k] = st.secrets[k]
except Exception:
    pass

from forgeai import llm  # noqa: E402
from forgeai.config import SETTINGS  # noqa: E402


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## 🏭 ForgeAI")
    st.caption("Brief + documents → tested agent + honest report")
    st.markdown(f"**Model:** `{SETTINGS.model}`  \n**Judge:** `{SETTINGS.judge_model}`  \n**Endpoint:** `{SETTINGS.base_url}`")

    @st.cache_data(ttl=60, show_spinner=False)
    def _ping(url, model):
        try:
            llm.chat([{"role": "user", "content": "ping"}], model=model, max_tokens=2, use_cache=False)
            return True
        except Exception as e:
            return str(e)[:120]

    ok = _ping(SETTINGS.base_url, SETTINGS.model)
    if ok is True:
        st.success("LLM endpoint reachable")
    else:
        st.error(f"LLM endpoint not reachable: {ok}")


def list_runs() -> list[Path]:
    return sorted([p for p in RUNS.glob("*") if (p / "agent.json").exists()], key=lambda p: p.name) if RUNS.exists() else []


tab_factory, tab_runs, tab_chat, tab_about = st.tabs(["🏭 Factory", "📊 Run explorer", "💬 Chat runner", "ℹ️ How it works"])

# ----------------------------------------------------------------------------- factory
with tab_factory:
    st.subheader("Build an agent")
    demos = {p.name: p for p in DEMOS.glob("*") if (p / "brief.md").exists()}
    c1, c2 = st.columns([2, 1])
    with c2:
        src = st.radio("Documents", ["Use a demo folder", "Upload files"], horizontal=False)
        demo = st.selectbox("Demo", list(demos)) if src == "Use a demo folder" else None
        uploads = st.file_uploader("PDF / MD / TXT / CSV / DOCX", accept_multiple_files=True) if src == "Upload files" else None
        run_name = st.text_input("Run name", value=f"ui_{demo or 'custom'}_{time.strftime('%m%d_%H%M')}")
        max_iters = st.slider("Max optimisation iterations", 0, 3, 3)
        n_cand = st.slider("Prompt candidates (tournament)", 1, 3, 2)
    with c1:
        default_brief = (demos[demo] / "brief.md").read_text() if demo else ""
        brief = st.text_area("One-paragraph brief", value=default_brief, height=170)

    def _docs_dir() -> Path | None:
        if demo:
            return demos[demo] / "docs"
        if uploads:
            d = Path(tempfile.mkdtemp(prefix="forge_up_"))
            for f in uploads:
                (d / Path(f.name).name).write_bytes(f.getvalue())
            return d
        return None

    S = st.session_state
    if st.button("① Inspect documents & generate clarifying questions", type="primary", disabled=not brief):
        from forgeai.docs import load_folder
        from forgeai.intake import build_inventory, interview

        dd = _docs_dir()
        if not dd:
            st.warning("Add documents first.")
        else:
            with st.spinner("Reading documents and drafting questions…"):
                docs = load_folder(dd)
                inv = build_inventory(docs, log=lambda *_: None)
                qs = interview(brief, inv, log=lambda *_: None)
            S.update(docs_dir=str(dd), inventory=inv, questions=qs, requirements=None)

    if S.get("questions"):
        st.markdown("#### Inventory")
        st.dataframe(pd.DataFrame([{"file": e["name"], "kind": e["kind"], "summary": e["summary"]} for e in S["inventory"]]), use_container_width=True, hide_index=True)
        st.markdown("#### Clarifying questions (≤5) — leave blank to accept the default assumption")
        answers = {}
        for i, q in enumerate(S["questions"], 1):
            answers[str(i)] = st.text_input(f"Q{i}. {q['question']}", placeholder=q["answer"], key=f"q{i}") or None
        S["answers"] = {k: v for k, v in answers.items() if v}

        if st.button("② Draft requirements + run groundability guard"):
            from forgeai.docs import chunk_documents, load_folder
            from forgeai.guard import apply_guard, run_guard
            from forgeai.intake import interview, write_requirements
            from forgeai.retrieval import Index

            with st.spinner("Writing requirements and auditing them against the documents…"):
                docs = load_folder(S["docs_dir"])
                clar = interview(brief, S["inventory"], answers=S["answers"], log=lambda *_: None)
                req = write_requirements(brief, S["inventory"], clar)
                g = run_guard(req, Index(chunk_documents(docs, "section", 220, 40)), [d.name for d in docs], log=lambda *_: None)
                S["requirements"] = apply_guard(req, g)

    if S.get("requirements"):
        from forgeai.intake import requirements_markdown

        req = S["requirements"]
        st.markdown("#### Human checkpoint — review the requirements")
        if req["groundability"]["warnings"]:
            st.warning("**Groundability guard:** the brief asks for things the documents cannot support. They will be refused, not hallucinated:\n\n"
                       + "\n".join(f"- {w}" for w in req["groundability"]["warnings"]))
        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown(requirements_markdown(req))
        with cc2:
            editable = {k: req[k] for k in ("agent_name", "purpose", "audience", "tone", "scope", "must_answer_topics", "must_refuse_topics", "capabilities_needed", "answer_format", "escalation_contact")}
            edited = st.text_area("Edit (JSON)", json.dumps(editable, indent=2), height=520)
        if st.button("③ Approve & build the agent", type="primary"):
            try:
                ed = json.loads(edited)
            except Exception as e:
                st.error(f"Invalid JSON: {e}")
                st.stop()
            from forgeai.pipeline import build

            final_req = {k: v for k, v in req.items() if k not in ("groundability", "supported_topics", "known_gaps")}
            final_req.update(ed)
            box = st.empty()
            lines: list[str] = []

            def ui_log(*a):
                lines.append(" ".join(str(x) for x in a))
                box.code("\n".join(lines[-40:]))

            with st.spinner("Factory running — this takes a while on a local model…"):
                res = build(brief, S["docs_dir"], RUNS / run_name, answers=S.get("answers"), max_iters=max_iters,
                            n_candidates=n_cand, log=ui_log, requirements_override=final_req)
            st.success(f"Built! Final score {res['scorecard']['overall']['passed']}/{res['scorecard']['overall']['n']}. Open it in the Run explorer / Chat runner.")

# ----------------------------------------------------------------------------- runs
with tab_runs:
    runs = list_runs()
    if not runs:
        st.info("No runs yet.")
    else:
        sel = st.selectbox("Run", runs, format_func=lambda p: p.name)
        sc = json.loads((sel / "scorecard.json").read_text())
        o = sc["overall"]
        m = st.columns(5)
        m[0].metric("Overall pass", f"{o['passed']}/{o['n']}", f"{o['pass_rate']:.0%}")
        m[1].metric("Answer accuracy", f"{(o['answer_accuracy'] or 0):.0%}")
        m[2].metric("Groundedness", f"{(o['groundedness'] or 0):.0%}")
        m[3].metric("Refusal recall", f"{(o['refusal_recall'] or 0):.0%}")
        m[4].metric("False refusals", f"{(o['false_refusal_rate'] or 0):.0%}")
        it = pd.DataFrame(sc["dev_by_iteration"])[["iteration", "version", "accepted", "pass_rate", "answer_accuracy", "groundedness", "refusal_recall"]]
        st.markdown("**Dev score per iteration**")
        st.line_chart(it.set_index("iteration")[["pass_rate", "answer_accuracy", "groundedness", "refusal_recall"]])
        sub = st.tabs(["Report", "Requirements", "Agent definition", "Eval set", "Results", "Iteration log", "Judge calibration"])
        with sub[0]:
            st.markdown((sel / "REPORT.md").read_text(), unsafe_allow_html=True)
        with sub[1]:
            st.markdown((sel / "03_requirements.md").read_text())
        with sub[2]:
            st.json(json.loads((sel / "agent.json").read_text()))
        with sub[3]:
            ev = json.loads((sel / "05_evalset.json").read_text())
            st.dataframe(pd.DataFrame(ev["cases"])[["id", "type", "split", "question", "expected_behavior", "key_facts", "expected_sources"]], use_container_width=True, hide_index=True)
            st.markdown("**Generation audit** (LLM claims that failed deterministic verification)")
            st.dataframe(pd.DataFrame(ev["audit"]["events"]), use_container_width=True, hide_index=True)
        with sub[4]:
            fr = json.loads((sel / "final_results.json").read_text())
            st.dataframe(pd.DataFrame(fr)[["id", "type", "split", "passed", "category", "question", "answer", "reason"]], use_container_width=True, hide_index=True)
        with sub[5]:
            st.json(json.loads((sel / "08_iteration_log.json").read_text()))
        with sub[6]:
            st.json(json.loads((sel / "06_judge_calibration.json").read_text()))

# ----------------------------------------------------------------------------- chat
with tab_chat:
    from forgeai.runtime import Agent

    runs = list_runs()
    choice = st.selectbox("Agent definition", [str(r / "agent.json") for r in runs] + ["(upload)"], key="chat_agent",
                          format_func=lambda s: s if s == "(upload)" else str(Path(s).relative_to(ROOT)))
    up = st.file_uploader("agent.json", type="json") if choice == "(upload)" else None

    @st.cache_resource(show_spinner="Loading agent…")
    def _load(path: str, mtime: float):
        return Agent.load(path)

    agent = None
    if choice != "(upload)":
        agent = _load(choice, Path(choice).stat().st_mtime)
    elif up:
        d = json.loads(up.getvalue())
        agent = Agent(d, base_dir=ROOT)
    if agent:
        d = agent.d
        st.caption(f"**{d['name']}** v{d.get('version', 0)} — {d.get('description', '')} · tools: {[t['name'] for t in d.get('tools', [])] or 'none'} · {len(agent.chunks)} chunks")
        key = f"hist_{choice}"
        st.session_state.setdefault(key, [])
        for msg in st.session_state[key]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("meta"):
                    with st.expander("sources & trace"):
                        st.json(msg["meta"])
        if q := st.chat_input("Ask the agent…"):
            with st.chat_message("user"):
                st.markdown(q)
            hist = [{"role": m["role"], "content": m["content"]} for m in st.session_state[key]]
            with st.chat_message("assistant"):
                with st.spinner("thinking…"):
                    r = agent.answer(q, hist)
                txt = ("🚫 " if r["refused"] else "") + r["answer"]
                st.markdown(txt)
                meta = {"citations": [{"label": p["label"], "doc": p["doc"], "section": p["section"]} for p in r["passages"] if p["label"] in r["citations"]],
                        "tools": r["tool_results"], "contract_violations": r["contract_violations"], "latency_s": r["latency_s"]}
                with st.expander("sources & trace"):
                    st.json(meta)
            st.session_state[key] += [{"role": "user", "content": q}, {"role": "assistant", "content": txt, "meta": meta}]

# ----------------------------------------------------------------------------- about
with tab_about:
    st.markdown((ROOT / "docs" / "ARCHITECTURE.md").read_text() if (ROOT / "docs" / "ARCHITECTURE.md").exists() else "See README.md")
