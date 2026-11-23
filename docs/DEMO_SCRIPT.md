# Demo video script (~6 minutes)

**0:00 – Hook (20s).** "ForgeAI takes one paragraph and a folder of documents and hands back a tested agent plus an
honest quality report. Everything runs on small local open models, so the interesting part is how the factory
catches itself lying."

**0:20 – Architecture (40s).** Show `docs/ARCHITECTURE.md` diagram: intake → guard → generator → evals → judge
calibration → tournament → critic loop → holdout + report. One sentence: "every LLM claim is paired with a
deterministic check."

**1:00 – Live run on an unseen-style input (90s).** In the terminal:
```bash
.venv/bin/python -m forgeai build --brief demos/hr_policy/brief.md --docs demos/hr_policy/docs --out runs/live_demo --interactive
```
Answer one clarifying question, approve the requirements at the checkpoint. Point at the guard output:
salary / payroll / bonus flagged UNSUPPORTED. Point at tool selection: all four tools rejected, with reasons.
(Let it keep running; cut to the committed run.)

**2:30 – The report (90s).** Open `runs/ship_spares/REPORT.md`:
- Headline 70% strict, failure audit "3 agent errors, 5 flawed tests, ≤89% if excused".
- Scorecard: iteration 1 **reverted** (74%→63%), iteration 2 accepted, early stop.
- Holdout 38%→62% — the split the optimiser never saw.
- Change log diff of one prompt section ("targeted fix, not regeneration").
- Judge calibration: canaries, verbosity trap, position probe, 9 overruled judge flags.

**4:00 – The five times the pipeline caught itself (40s).** README section "Where the pipeline caught itself lying".

**4:40 – Runnable product (50s).** `streamlit run app.py` → Run explorer chart → Chat runner: ask the HR agent a
sick-leave question (cited answer), then "When is payroll credited?" (refused, gap). Switch to the spares agent:
"What do 4 fire pump mechanical seals cost?" (CSV lookup + calculator trace).

**5:30 – Stretch goals (30s).** `BASELINE_COMPARISON.md` (factory 96% vs human 92%) and `REGRESSION.md`
(stale test detected after the leave policy changed).

**6:00 – Close.** "It doesn't claim 100%. It tells you what fails, whether it's the agent or the test, and why."
