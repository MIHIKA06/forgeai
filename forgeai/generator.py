"""Stage 3 - agent generator: tool selection (LLM proposal + deterministic gates), retrieval
parameters (from document statistics), sectioned system-prompt candidates (so later fixes
can patch ONE section), and the output contract. Output: a declarative agent.json."""
from __future__ import annotations

import json
import re
from typing import Callable

from . import llm, tools
from .config import SETTINGS
from .docs import Document, profile
from .runtime import DEFAULT_CONTRACT, SCHEMA_VERSION
from .textutil import norm, quote_in_text

SECTIONS = ["role", "audience_tone", "scope", "grounding_rules", "refusal_policy", "answer_style", "tool_use"]
TITLES = {"role": "Role", "audience_tone": "Audience & tone", "scope": "Scope", "grounding_rules": "Grounding rules",
          "refusal_policy": "Refusal policy", "answer_style": "Answer style", "tool_use": "Tool use"}

STYLES = {
    "A_strict": "Strict and terse. Lead with the direct answer in one or two sentences, then the key condition or exception. Prefer quoting exact figures from the passages.",
    "B_structured": "Helpful and structured. Start with a one-line answer, then short bullet points for conditions, steps or exceptions. Friendly but professional.",
    "C_cautious": "Cautious advisor. Answer only what the passages state explicitly; when a question is ambiguous, answer the most likely reading and state the assumption; flag any exception that might apply.",
}


def _mentions_gap(sentence: str, gaps: list[str]) -> bool:
    sw = {w[:5] for w in re.findall(r"[a-z]{4,}", sentence.lower())}
    for g in gaps:
        gw = {w[:5] for w in re.findall(r"[a-z]{4,}", g.lower())}
        if gw and len(gw & sw) / len(gw) >= 0.5:
            return True
    return False


def req_text(req: dict) -> str:
    """Requirement text that may justify a tool. Sentences about KNOWN GAPS are excluded:
    a tool must not be attached to serve a topic the guard already ruled out of scope."""
    gaps = req.get("known_gaps", [])
    brief_sents = re.split(r"(?<=[.!?])\s+", req.get("brief", ""))
    caps_ok = [m.get("capability", "") for m in req.get("groundability", {}).get("capabilities", []) if m.get("satisfied_by") != "unsupported"]
    if not req.get("groundability"):
        caps_ok = req.get("capabilities_needed", [])
    parts = [s for s in brief_sents if not _mentions_gap(s, gaps)]
    parts += [req.get("purpose", ""), req.get("scope", ""), " ".join(req.get("supported_topics", req.get("must_answer_topics", []))),
              " ".join(caps_ok), req.get("answer_format", "")]
    parts += [c.get("answer", "") for c in req.get("clarifications", []) if c.get("source") == "requester"]
    return "\n".join(p for p in map(str, parts) if not _mentions_gap(p, gaps) or p in caps_ok)


# --------------------------------------------------------------------------- tools
def select_tools(req: dict, docs: list[Document], log: Callable = print) -> tuple[list[dict], list[dict]]:
    files = [d.name for d in docs]
    has_table = any(d.kind == "table" for d in docs)
    rtext = req_text(req)
    # Signal words must come from the REQUESTER's words (brief + their answers), not from text an
    # LLM wrote while drafting requirements - otherwise the model can justify a tool by inventing a need.
    gaps = req.get("known_gaps", [])
    human = [s for s in re.split(r"(?<=[.!?])\s+", req.get("brief", "")) if not _mentions_gap(s, gaps)]
    human += [c.get("answer", "") for c in req.get("clarifications", []) if c.get("source") == "requester"]
    rnorm = norm(" ".join(human))
    cap_map = {m.get("satisfied_by"): m for m in req.get("groundability", {}).get("capabilities", [])}
    registry_txt = "\n".join(f"- {t.name}: {t.description} USE WHEN: {t.when_to_use}" for t in tools.REGISTRY.values())
    view = {k: req[k] for k in ("purpose", "audience", "scope", "must_answer_topics", "capabilities_needed") if k in req}
    view["brief"] = req.get("brief", "")
    view["NOT_SUPPORTED_will_be_refused"] = req.get("known_gaps", [])
    try:
        out = llm.chat_json(llm.render("tool_selection", requirements=json.dumps(view, indent=2), files=", ".join(files), tools=registry_txt),
                            validate=llm.require_keys("decisions"), max_tokens=900)
        llm_dec = {d.get("tool"): d for d in out["decisions"] if isinstance(d, dict)}
    except Exception as e:
        log(f"  ! tool selection LLM failed ({e}); using deterministic signals only")
        llm_dec = {}

    attached, rejected = [], []
    for name, tool in tools.REGISTRY.items():
        d = llm_dec.get(name, {})
        llm_says = bool(d.get("attach"))
        evidence = str(d.get("evidence", "") or "")
        ev_ok = bool(evidence) and quote_in_text(evidence, " ".join(human), 0.8)
        signals = [s for s in tool.signals if s in rnorm]
        cap = cap_map.get(name)
        prereq_ok = has_table if name == "csv_lookup" else True
        # Decision rule: needs (LLM vote or capability mapping) AND prerequisite AND independent textual evidence.
        votes = llm_says or bool(cap)
        textual = bool(signals) or (ev_ok and bool(cap))
        if name == "csv_lookup" and has_table and signals:
            votes = True  # tables + lookup language in the brief: exact lookup beats fuzzy retrieval
        attach = votes and prereq_ok and textual
        why = []
        if not prereq_ok:
            why.append(f"prerequisite failed: {tool.prerequisite}")
        if votes and not textual:
            why.append("LLM wanted it but the requester's own words give no evidence for it (no signal words in brief/answers)")
        if not votes:
            why.append("not needed by any requirement")
        rec = {"name": name, "llm_vote": llm_says, "llm_reason": d.get("reason", ""), "evidence_quote": evidence if ev_ok else "",
               "signal_words": signals, "capability": cap.get("capability") if cap else None}
        if attach:
            rec["justification"] = d.get("reason") or (f"capability '{cap['capability']}'" if cap else f"requirements mention {signals}")
            attached.append(rec)
            log(f"  + attach {name}: {rec['justification']}")
        else:
            rec["rejected_because"] = "; ".join(why) or "not needed"
            rejected.append(rec)
            log(f"  - reject {name}: {rec['rejected_because']}")
    return attached, rejected


# --------------------------------------------------------------------------- retrieval params
def retrieval_params(docs: list[Document]) -> dict:
    p = profile(docs)
    med = p["median_section_words"] or 200
    size = int(min(400, max(120, med * 1.3)))
    probe = llm.embed(["probe"])
    return {
        "strategy": "section",
        "chunk_size": size,
        "chunk_overlap": size // 6,
        "top_k": 6 if p["n_docs"] > 3 or p["has_tables"] else 5,
        "mode": "hybrid" if probe else "bm25",
        "query_rewrite": False,
        "rationale": f"median section {med} words -> chunk {size}; {p['n_docs']} docs; embeddings {'available' if probe else 'unavailable'}",
    }


# --------------------------------------------------------------------------- system prompt
def assemble(sections: dict) -> str:
    return "\n\n".join(f"## {TITLES[k]}\n{str(sections.get(k, '')).strip()}" for k in SECTIONS)


def parse_sections(prompt: str) -> dict:
    inv = {v: k for k, v in TITLES.items()}
    out, cur = {}, None
    for line in prompt.split("\n"):
        m = re.match(r"^## (.+)$", line.strip())
        if m and m.group(1).strip() in inv:
            cur = inv[m.group(1).strip()]
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def lint_sections(sec: dict, req: dict, tool_names: list[str]) -> tuple[dict, list[str]]:
    """Deterministic lint: the generated prompt MUST carry certain clauses. Patch them in."""
    fixes = []
    for k in SECTIONS:
        if not str(sec.get(k, "")).strip():
            sec[k] = ""
            fixes.append(f"section '{k}' was empty")
    g = sec["grounding_rules"]
    if not re.search(r"only|solely|exclusively", g, re.I):
        sec["grounding_rules"] = g + "\n- Answer only from the CONTEXT passages (and tool results). Never use outside knowledge."
        fixes.append("added 'only from context' rule")
    if not re.search(r"cite|citation|\[S", sec["grounding_rules"], re.I):
        sec["grounding_rules"] += "\n- Cite the passage labels (e.g. S2) that support each answer."
        fixes.append("added citation rule")
    rp = sec["refusal_policy"]
    missing = [t for t in req["must_refuse_topics"] + req.get("known_gaps", []) if norm(t)[:25] not in norm(rp)]
    if missing:
        sec["refusal_policy"] = rp + "\n- Always refuse: " + "; ".join(missing) + "."
        fixes.append(f"added {len(missing)} missing refusal topics")
    if not tool_names:
        sec["tool_use"] = "No tools are available. Do not mention tools."
    else:
        if re.search(r"no tools", sec["tool_use"], re.I):
            sec["tool_use"] = ""
            fixes.append("removed 'no tools' claim although tools are attached")
        for n in tool_names:
            if n not in sec["tool_use"]:
                sec["tool_use"] += f"\n- {n}: {tools.REGISTRY[n].when_to_use}"
                fixes.append(f"documented tool {n}")
        for n in tools.REGISTRY:
            if n not in tool_names and n in sec["tool_use"]:
                sec["tool_use"] = re.sub(rf".*{n}.*\n?", "", sec["tool_use"])
                fixes.append(f"removed mention of unattached tool {n}")
    return sec, fixes


def prompt_candidates(req: dict, tool_names: list[str], n: int = 3, log: Callable = print) -> list[dict]:
    view = {k: req[k] for k in ("agent_name", "purpose", "audience", "tone", "scope", "must_refuse_topics", "answer_format", "escalation_contact") if k in req}
    view["must_answer_topics"] = req.get("supported_topics", req["must_answer_topics"])
    cands = []
    for style_id, style in list(STYLES.items())[:n]:
        try:
            sec = llm.chat_json(
                llm.render("system_prompt", requirements=json.dumps(view, indent=2), gaps=json.dumps(req.get("known_gaps", [])),
                           tools=json.dumps(tool_names) if tool_names else "none", style=style),
                validate=llm.require_keys("role", "grounding_rules", "refusal_policy"), temperature=0.4, max_tokens=1400)
        except Exception as e:
            log(f"  ! candidate {style_id} failed: {e}")
            continue
        sec = {k: (("\n".join(f"- {x}" for x in v)) if isinstance(v, list) else str(v)) for k, v in sec.items() if k in SECTIONS}
        sec, fixes = lint_sections(sec, req, tool_names)
        cands.append({"id": style_id, "style": style, "sections": sec, "prompt": assemble(sec), "lint_fixes": fixes})
        log(f"  candidate {style_id}: {len(assemble(sec).split())} words, lint fixes: {fixes or 'none'}")
    return cands


# --------------------------------------------------------------------------- definition
def build_definition(req: dict, docs: list[Document], docs_rel_path: str, attached: list[dict], rejected: list[dict], prompt: dict, retrieval: dict) -> dict:
    concise = re.search(r"concise|brief|short|terse", req.get("tone", "") + req.get("answer_format", ""), re.I)
    contract = dict(DEFAULT_CONTRACT)
    contract["max_words"] = 120 if concise else 180
    contract["refusal_message"] = f"I can't answer that from the documents I have access to. Please contact {req.get('escalation_contact', 'the responsible team')}."
    return {
        "schema_version": SCHEMA_VERSION,
        "name": re.sub(r"[^A-Za-z0-9_\-]+", "-", req["agent_name"]).strip("-") or "agent",
        "description": req["purpose"],
        "version": 0,
        "knowledge": {"docs_path": docs_rel_path, "files": [d.name for d in docs]},
        "system_prompt": prompt["prompt"],
        "prompt_candidate": prompt["id"],
        "retrieval": retrieval,
        "tools": [{"name": t["name"], "justification": t["justification"], "evidence_quote": t["evidence_quote"]} for t in attached],
        "tools_rejected": [{"name": t["name"], "reason": t["rejected_because"]} for t in rejected],
        "output_contract": contract,
        "generation": {"model": SETTINGS.model, "temperature": 0.1},
        "scope": {"must_answer": req.get("supported_topics", req["must_answer_topics"]), "must_refuse": req["must_refuse_topics"],
                  "known_gaps": req.get("known_gaps", [])},
        "provenance": {"factory": "ForgeAI 1.0", "judge_model": SETTINGS.judge_model},
    }
