# How ForgeAI works

ForgeAI turns **a one-paragraph brief + a folder of documents** into a **declarative, tested agent** and an
**honest quality report**, running unattended on small open models (default: Qwen2.5-7B builds, Llama-3.1-8B judges).

```
 brief.md + docs/
      │
 [1] Intake interviewer ──► 01_inventory.json, 02_clarifications.json (≤5 questions; defaults recorded as assumptions)
      │
 [2] Groundability guard ─► 03_requirements.json/.md  (topics: supported / partial / UNSUPPORTED → refused + tested)
      │        (human checkpoint: approve / edit requirements — CLI --interactive or UI)
 [3] Agent generator ─────► 04_prompt_candidates.json (tools: LLM vote + deterministic gates; retrieval from doc stats;
      │                                                sectioned prompt + lint)
 [4] Eval generator ──────► 05_evalset.json  (answerable, multi-doc, ambiguous, out-of-scope, gap probes, tool cases;
      │                                        every LLM claim verified; dev/holdout split)
 [5] Judge calibration ───► 06_judge_calibration.json (planted canaries measure the LLM judge before trusting it)
      │
 [6] Prompt tournament ───► 07_tournament.json, agent_v0.json (2–3 candidate prompts, eval set picks the winner)
      │
 [7] Critic–optimizer ────► iterations/iter_N.json, 08_iteration_log.json, agent.json
      │   classify failures → ONE targeted fix per category → re-run full dev set → accept or revert (max 3)
      │
 [8] Holdout + report ────► 09_holdout.json, scorecard.json, final_results.json, REPORT.md, budget.json
```

## Design principle: distrust every LLM output

Every stage runs on a small model that *will* sometimes lie. Each LLM claim is paired with a deterministic check:

| LLM claims… | ForgeAI verifies… |
|---|---|
| "this topic is covered, here's the evidence quote" (guard) | the quote really exists in the retrieved passages, and the topic's words occur there; final verdict = the **more pessimistic** of LLM and checker |
| "this tool is needed because …" (generator) | the tool's prerequisite holds (e.g. a CSV exists) **and** its need is evidenced in the requirements text — *excluding* sentences about topics the guard already ruled out |
| "the answer to this test question is X, copied from the passage" (eval gen) | each key fact is found in the source passage; unverifiable facts are dropped, leaky/duplicate questions dropped; the audit is saved |
| "this out-of-scope question is unanswerable" (eval gen) | a *different* model checks the top passages don't answer it |
| "the answer states fact X" (judge) | numbers in X must literally appear in the answer; the judge's accuracy is measured on planted canaries first |
| "this prompt patch fixes the failures" (optimizer) | the full dev set is re-run; regressions are reverted; patches that copy eval answers into the prompt are rejected |
| "the agent improved" (report) | an untouched **holdout split** is scored before and after the loop to expose overfitting |

## The judge

* **Deterministic first:** fact matching (numbers must match exactly, ≥70 % of content words), citation of the expected
  source, refusal detection, *ungrounded numbers* (numbers in the answer that appear in no passage/tool output).
* **LLM second (different model family):** decomposed per-fact verdicts (`stated / contradicted / missing`) + unsupported claims.
* **Bias defences:** per-fact binary verdicts instead of a 1–10 score (verbosity), "length is irrelevant" instruction,
  fact-order reversal probe (position), both-order pairwise comparisons where inconsistent = tie (position),
  different model family (self-preference), canaries with *verbose-but-wrong* answers (verbosity) and *corrupted-number*
  answers (laundering). If the LLM judge scores < 75 % on canaries it is demoted to **advisory** (can veto, never grant credit).

## Failure taxonomy and targeted fixes

| Category | Detected when | Targeted fix |
|---|---|---|
| retrieval_miss | expected source not in retrieved passages | offline grid search over top_k / mode / chunk size measuring source-recall on **all** dev questions; else enable query rewriting |
| wrong_refusal | refused although the source was retrieved | rewrite the *Refusal policy* (then *Grounding rules*) section only |
| hallucination | answered an out-of-scope question, or ungrounded numbers / judge-flagged claims | rewrite *Grounding rules* / *Refusal policy*, temperature → 0 |
| prompt_defect | right passages, answered, but facts/citations/tool use missing | rewrite *Answer style* or *Tool use* section only |

The system prompt is generated as named sections precisely so that a fix can replace **one section** (a diff is logged)
instead of regenerating the agent.

## The generated agent

`agent.json` is pure data: system prompt, retrieval config, attached tools (with justification), output contract
(`{"answer", "citations", "refused"}`), scope (must-answer / must-refuse / known gaps). `forgeai/runtime.py` is the generic
runner (CLI `python -m forgeai chat --agent …` or the UI chat tab) that loads any definition.
