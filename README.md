# 🏭 ForgeAI — the agent that builds (and distrusts) agents

> One paragraph + a folder of documents → a **declarative, tested agent** (system prompt, retrieval config, tools,
> output contract) + an **auto-generated eval set** + a **critic–optimizer loop** + an **honest quality report**.
> Runs unattended on small **local open models** (Qwen2.5-7B builds, Llama-3.1-8B judges, via Ollama).

The core idea: *every stage runs on a small model that will sometimes lie, so every LLM claim is paired with a
deterministic check that can catch it.* See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

<!-- RESULTS -->

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
