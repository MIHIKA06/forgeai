# 🏭 ForgeAI — the agent that builds (and distrusts) agents

> One paragraph + a folder of documents → a **declarative, tested agent** (system prompt, retrieval config, tools,
> output contract) + an **auto-generated eval set** + a **critic–optimizer loop** + an **honest quality report**.
> Runs unattended on small **local open models** (Qwen2.5-7B builds, Llama-3.1-8B judges, via Ollama).

**🌐 Live app:** https://forgeai-oceanai.streamlit.app (Run explorer + Chat runner, served by open models on Groq; build new agents locally with Ollama).

The core idea: *every stage runs on a small model that will sometimes lie, so every LLM claim is paired with a
deterministic check that can catch it.* See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Results of the two committed demo runs

| | HR policy assistant | Ship-spares procurement assistant |
|---|---|---|
| Documents | 3 PDFs | 1 CSV catalogue (42 rows) + 3 PDFs |
| Guard flagged (brief asked, docs can't support) | salary structure, payroll dates, bonus calculation | live supplier stock levels, order tracking |
| Tools attached | **none** (calculator/date proposed by the LLM, rejected: no evidence in the requester's words) | `csv_lookup`, `calculator` (weather & date rejected) |
| Eval set | 25 generated cases (dev 17 / holdout 8) | 27 generated cases incl. 3 tool cases (dev 19 / holdout 8) |
| Prompt tournament | 3 candidates, winner `C_cautious` | 3 candidates, winner `A_strict` |
| Optimiser loop | iter 1: hallucination fix → dev 94% → 100% | iter 1: fix **reverted** (74% → 63%); iter 2: lateral fix accepted; early stop |
| Holdout (never seen by optimiser) | 88% → 88% (no gain: the dev gain does not generalise, and the report says so) | 38% → 62% |
| **Final (strict)** | **24/25 (96%)** | **19/27 (70%)** |
| Failure audit | 1 agent error | 3 agent errors, 5 flawed generated tests → ≤ 89% if excused |

Full evidence per run in [`runs/hr_policy/REPORT.md`](runs/hr_policy/REPORT.md) and
[`runs/ship_spares/REPORT.md`](runs/ship_spares/REPORT.md). Stretch-goal evidence:
[`BASELINE_COMPARISON.md`](runs/hr_policy/BASELINE_COMPARISON.md) (factory 96% vs my hand-written agent 92% on the same
evals and judge) and [`REGRESSION.md`](runs/hr_policy_regression/REGRESSION.md) (leave policy v5: one test correctly
detected as *stale*, the agent gives the new 15-day answer; two breaks traced to model instability, not the edit).

A third, fully **uncached run from scratch** of the HR brief is committed unedited in [`runs/live_demo/`](runs/live_demo/REPORT.md):
20/25 (80%); its round-1 fix lowered the dev score and was automatically reverted. Run-to-run variation between it
and `runs/hr_policy` (96%) shows how much a small model's output varies between runs, which is exactly why the
report shows a holdout split and a failure audit instead of a single number.

Uncached wall time on an M-series Mac with Ollama: ~7 min (HR) and ~15 min (spares) on a quiet machine; up to ~40 min under memory pressure. The committed artifacts were
re-generated from the on-disk LLM cache after the last judge fix, so `budget.json` shows cache hits and near-zero wall time.

### Where the pipeline caught *itself* lying (found while building this)

1. **Requirements writer dropped inconvenient asks.** In one run the LLM silently removed "payroll dates" and "bonus"
   from the must-answer list, so the guard could never flag them → added the brief-asks completeness check.
2. **Tool selection justified by invented needs.** The requirements LLM wrote "today's date for deadlines" for the
   spares brief (the requester never mentioned dates) and that became the evidence for `current_date` → tool evidence
   must now come from the requester's own words.
3. **The 8B judge flags verbatim-supported sentences as "unsupported claims".** Groundedness was 50% for answers that
   quoted the policy → the judge's veto now needs deterministic agreement (12 + 9 flags overruled, reported).
4. **The independent failure reviewer was a yes-man.** It excused 8/8 failures, including flat refusals → deterministic
   rules it cannot overrule (refusing a question whose verified source was retrieved is always an agent error).
5. **Fuzzy matching hid a document change.** "10 days" → "15 days" is ~99% similar → stale-test detection uses exact
   normalised containment of the most relevant source sentence.

## Quick start

```bash
# 1. local open models (or point FORGE_BASE_URL at any OpenAI-compatible endpoint, e.g. Groq)
brew install ollama && brew services start ollama
ollama pull qwen2.5:7b && ollama pull llama3.1:8b && ollama pull nomic-embed-text

# 2. python env
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt

# 3. run the factory on ANY brief + folder, unattended
.venv/bin/python -m forgeai build --brief "I need an assistant that ..." --docs path/to/folder --out runs/my_agent

# 4. chat with the generated agent (generic runner, loads any agent.json)
.venv/bin/python -m forgeai chat --agent runs/my_agent/agent.json

# 5. web UI: factory wizard with human checkpoint, run explorer, chat runner
.venv/bin/python -m streamlit run app.py
```

Add `--interactive` to answer the clarifying questions and approve/edit the requirements in the terminal
(human checkpoint). Without it the run is unattended: default assumptions are recorded in `02_clarifications.json`.

| Command | What it does |
|---|---|
| `build --brief --docs --out [--interactive] [--max-iters 3] [--candidates 3] [--budget-tokens N] [--budget-minutes M]` | full factory |
| `chat --agent agent.json` | generic chat runner (`:debug` shows retrieval) |
| `eval --agent X --evalset Y [--split dev/holdout/all]` | score any definition on any eval set |
| `regress --run runs/x --docs new_docs [--rebuild]` | documents changed → re-run the OLD eval set, report broke / fixed / *stale tests* |
| `baseline --run runs/x --agent human.json` | factory vs hand-written agent on the same evals + judge |

Environment: `FORGE_BASE_URL`, `FORGE_API_KEY`, `FORGE_MODEL`, `FORGE_JUDGE_MODEL`, `FORGE_EMBED_MODEL`,
`FORGE_WORKERS` (parallel eval calls), `FORGE_CACHE` (1 = cache LLM calls on disk for reproducible re-runs).

## The nine requirements → where they live

| # | Requirement | Implementation | Artifact |
|---|---|---|---|
| 1 | Intake interviewer (≤5 questions) | `forgeai/intake.py` — doc inventory → questions with default assumptions (hard-capped at 5) → requirements; a *brief-asks completeness check* restores any ask the LLM silently dropped | `01_inventory.json`, `02_clarifications.json`, `03_requirements.md` |
| 2 | Groundability guard | `forgeai/guard.py` — LLM auditor verdict + evidence quote, **verified** against the passages; final = more pessimistic of LLM/deterministic; capabilities mapped to tools or flagged *unsupported*; gaps become refusal rules **and** refusal tests | `03_requirements.md` (guard table) |
| 3 | Agent generator | `forgeai/generator.py` — tools by LLM vote + prerequisite + textual evidence (excluding out-of-scope sentences); retrieval params from doc statistics; sectioned prompts + lint | `agent.json`, `04_prompt_candidates.json` |
| 4 | Eval generator (≥20, generated) | `forgeai/evalgen.py` + `forgeai/prompts/evalgen_*.md` — answerable, multi-doc, ambiguous, out-of-scope, gap probes, tool cases; each key fact verified in its source; audit trail; dev/holdout split | `05_evalset.json` |
| 5 | Judge with bias defences | `forgeai/judge.py` — deterministic + different-family LLM, per-fact verdicts, canary calibration, position probe, both-order pairwise | `06_judge_calibration.json` |
| 6 | Critic–optimizer (≤3 iters) | `forgeai/optimizer.py` — 4-way taxonomy → one targeted fix per category → full dev re-run → accept/revert; every change logged with diff, addressed cases, before/after | `iterations/`, `08_iteration_log.json` |
| 7 | Honest reporting | `forgeai/report.py` — what still fails and why, holdout generalisation gap, overfitting & "too-good" warnings, judge reliability, budget | `REPORT.md`, `scorecard.json` |
| 8 | Runnable product | `forgeai/runtime.py` — generic runner for any definition; CLI + Streamlit chat | `agent.json` |
| 9 | Two full demos | HR policy (3 PDFs) and ship-spares procurement (CSV + 3 PDFs) | `runs/hr_policy/`, `runs/ship_spares/` |

**Stretch goals implemented:** prompt tournament (with position-debiased pairwise tie-break), budget enforcement
with early stopping, human checkpoint (CLI + UI), factory-vs-human baseline, regression mode (with stale-test
detection), Streamlit UI + Docker/HF-Spaces config.

## Things I did that the brief did not ask for (and why)

* **Holdout split.** The optimiser only ever sees the dev split; the report shows v0→final on an untouched holdout so a
  dev-score gain bought by overfitting is visible.
* **Judge canaries.** Before trusting the LLM judge, ForgeAI plants answers whose verdict it *knows* (gold, terse-correct,
  corrupted numbers, verbose-but-wrong) and measures the judge. An unreliable judge is automatically demoted to advisory.
* **Anti-teaching-to-the-test.** A prompt patch that copies an eval answer into the system prompt is rejected.
* **Retrieval fixes are tested offline** across the whole dev set (no LLM calls) before being applied, so a fix can't trade
  one miss for two.
* **Stale-test detection in regression mode.** When documents change, a failing old test may be the *test* that's wrong
  (its fact no longer exists in the docs). ForgeAI separates "agent broke" from "test is stale".
* **Brief-asks completeness check.** Small models quietly drop inconvenient asks while writing requirements; ForgeAI
  re-extracts the asks and restores any that vanished so the guard can flag them.

## Repository layout

```
forgeai/            the factory (one module per stage) + prompts/ (every generation prompt, committed)
demos/              two briefs + synthetic document sets + SYNTHESIS_PROMPTS.md + synthesize.py
runs/               complete artifacts of the demo runs (requirements, definitions, eval sets, iteration logs, scorecards, reports)
baselines/          hand-written human agent for the baseline comparison
tests/              deterministic unit tests (no LLM)
app.py              Streamlit UI
docs/ARCHITECTURE.md
```

## Hosting

The UI runs anywhere Streamlit runs. A hosted box has no local GPU, so set the secrets in
`.streamlit/secrets.toml.example` to any OpenAI-compatible endpoint serving open models (e.g. Groq's free tier);
embeddings fall back to BM25 automatically when the endpoint has none. `Dockerfile` targets Hugging Face Spaces (Docker SDK).
