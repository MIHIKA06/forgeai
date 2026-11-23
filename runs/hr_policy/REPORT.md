# ForgeAI quality report — `HRAssistant`

> **Final agent v1: 24/25 eval cases pass (96%).** Dev split 94% → 100% over 1 optimisation iteration(s); untouched holdout split 88% → 88%.
> **Failure audit:** of 1 failures, an independent reviewer (judge model + source passages) attributes **1 to the agent**, **0 to flawed auto-generated tests or grading**, 0 unclear. The strict score above stands; if every suspected test error were excused it would be at most 96%. Both numbers are reported because the eval set is itself machine-generated.

## What still fails and why

The main weaknesses are in the refusal to answer out-of-scope questions and the handling of ambiguous or incomplete information. The root causes are a lack of clear refusal rules and insufficient context understanding. The next step is to add a refusal mechanism for out-of-scope questions and improve context retrieval.

| Case | Type | Split | Category | Judge verdict | Deterministic evidence | Independent review | Root-cause hypothesis |
|---|---|---|---|---|---|---|---|
| O01 | out_of_scope | holdout | hallucination | answered a question it should have refused | answered instead of refusing; it cited ['workplace_policy.pdf'] - retrieved passages on a related topic (leave_policy.pdf, travel_expense_policy.pdf,  | **agent_error**: reviewer said test_error ('The policy does not explicitly state that being late once is a serious offense, and the as') - overruled: answere | The assistant failed to recognize the question as out-of-scope due to a lack of clear refusal rules. |

<details><summary>Questions and answers of the failing cases</summary>

- **O01** Q: Can I get a warning for being late once or will it be considered a serious offense?  
  A: The policy does not specify the consequences of being late once. However, habitual lateness may be considered unauthorised absence if it leads to more than 3 consecutive working days of absence without approved leave, which could then be treated as a serious offense under the Code of Conduct. Please consult the HR Department for specific guidelines on lateness.

</details>

## Per-iteration scorecard (dev split — the only split the optimiser sees)

| Iter | Agent ver | Dev pass | Answer acc | Grounded | Refusal recall | False refusals | Retrieval hit | Failure categories | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| 0 | v0 | 16/17 (94%) | 100% | 100% | 80% | 0% | 92% | hallucination:1 | baseline |
| 1 | v1 | 17/17 (100%) | 100% | 100% | 100% | 0% | 92% | – | accepted |

## Generalisation check (holdout split — never shown to the optimiser)

| Agent | Holdout pass | Answer acc | Grounded | Refusal recall | False refusals |
|---|---|---|---|---|---|
| v0 (before loop) | 7/8 (88%) | 100% | 100% | 67% | 0% |
| v1 (final) | 7/8 (88%) | 100% | 100% | 67% | 0% |

## Change log

### Iteration 1 — accepted (dev 94% → 100%)
Newly passing: ['O04'] · Newly failing: –

- **hallucination → `prompt:grounding_rules`**: Added refusal to answer out-of-scope questions and escalation policy for specific issues.
  - Why: The assistant stated things not supported by the passages, or answered questions that are out of scope instead of refusing.
  - Addressed failures: ['O04'] · actually fixed: ['O04']

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -10,3 +10,3 @@
 ## Grounding rules
-Answers only from provided CONTEXT passages; uses [S1], [S2], etc. labels; never invents facts, numbers, or policies; cites passages when policies conflict
+Answers only from provided CONTEXT passages; uses [S1], [S2], etc. labels; never invents facts, numbers, or policies; cites passages when policies conflict; refuses to answer questions outside scope; escalates to HR Department for disciplinary actions, performance reviews, salary increments, promotions, medical advice, or legal advice.
 
```
</details>

_Stopped: all dev cases pass_

_Loop stop reason: all dev cases pass_

## Requirements & groundability guard

- **Purpose:** To provide HR policy information to shore staff in Mumbai and Chennai offices.
- **Audience:** Shore-based employees at Shore Staff Seacrest Ship Management Pvt Ltd.
- **Approval:** auto-approved (unattended run)
- **Guard status:** `gaps_flagged` (topic coverage 62%)
  - ⚠️ Topic 'Salary Structure' is not supported by the documents (What is the structure of salaries, including components like basic salary, HRA, and allowances? How are salaries calculated and reviewed? Are there different salary scales for different positions or levels of experience?).
  - ⚠️ Topic 'payroll dates' is not supported by the documents (When are payroll dates for encashing unused annual leave and final settlements?).
  - ⚠️ Topic 'annual performance bonus calculation' is not supported by the documents (What is the formula or process for calculating the annual performance bonus?).

## Tool selection

| Tool | Decision | Reason |
|---|---|---|
| csv_lookup | ❌ rejected | prerequisite failed: knowledge folder contains at least one CSV/TSV file; LLM wanted it but the requester's own words give no evidence for it (no signal words in brief/answers) |
| calculator | ❌ rejected | LLM wanted it but the requester's own words give no evidence for it (no signal words in brief/answers) |
| weather_forecast | ❌ rejected | not needed by any requirement |
| current_date | ❌ rejected | not needed by any requirement |

## Prompt tournament

| Candidate | Dev pass | Mean fact score | Lint fixes | Result |
|---|---|---|---|---|
| A_strict | 16/17 | 0.902 | 2 |  |
| B_structured | 15/17 | 0.861 | 2 |  |
| C_cautious | 16/17 | 0.931 | 1 | 🏆 winner |

Tie-break (position-debiased pairwise judge): C_cautious vs A_strict: {'A': 0, 'B': 0, 'tie': 6} (each pair judged in both orders; inconsistent verdicts count as tie)

## Eval set

25 generated cases: {'answerable': 12, 'ambiguous': 3, 'gap_probe': 3, 'multi_doc': 2, 'out_of_scope': 5} · splits {'holdout': 8, 'dev': 17}.
Generation audit (claims checked deterministically): {'multi_doc:dropped': 1, 'ambiguous:dropped': 1}.

## Judge calibration (planted canaries)

- Judge model `llama3.1:8b` vs agent model `qwen2.5:7b` → self-preference guard: different model family
- LLM judge accuracy on 20 canaries: 100% · deterministic checker: 100%
- Verbosity trap (long, fluent, wrong answers) caught: 100% · false-accept rate on corrupted answers: 0%
- Position consistency (fact order reversed): 100%
- Resulting judge mode: **full** — LLM may credit paraphrased facts the string matcher missed; numbers always checked deterministically
- Judge/deterministic disagreements during final eval: 15
- 'Unsupported claim' flags raised by the LLM judge but **overruled** because the claim is found verbatim-ish in the passages/question: 12 (observed failure mode of the 8B judge: it flags sentences copied from the passages; its groundedness veto is therefore only accepted when the deterministic checker agrees)

## Final agent definition

- Retrieval: `{"strategy": "section", "chunk_size": 120, "chunk_overlap": 20, "top_k": 5, "mode": "hybrid", "query_rewrite": false}`
- Output contract: JSON `{answer, citations, refused}`, max 120 words, citations required
- Prompt candidate: C_cautious

<details><summary>System prompt</summary>

```
## Role
HRAssistant, providing HR policy information to Shore Staff Seacrest Ship Management Pvt Ltd. employees in Mumbai and Chennai offices

## Audience & tone
Friendly but precise, avoiding legal advice or individual cases

## Scope
Answers HR policy questions on leave, travel and expenses, work rules, and salary structure (excluding salary structure, payroll dates, and annual performance bonus calculation)

## Grounding rules
Answers only from provided CONTEXT passages; uses [S1], [S2], etc. labels; never invents facts, numbers, or policies; cites passages when policies conflict; refuses to answer questions outside scope; escalates to HR Department for disciplinary actions, performance reviews, salary increments, promotions, medical advice, or legal advice.

## Refusal policy
Refuses to discuss disciplinary actions, performance reviews, salary increments, promotions, medical advice, legal advice, or personal data; escalates to HR Department for such issues
- Always refuse: Salary Structure; payroll dates; annual performance bonus calculation.

## Answer style
Short paragraph with policy citation; bullet steps for procedures; states assumptions for ambiguous questions; flags exceptions

## Tool use
No tools are available. Do not mention tools.
```
</details>

## Budget

- Tokens: 163,130 of 3,000,000 · LLM calls: 227 (cache hits 227) · wall time 0.0 min

| Stage | Calls | Tokens | LLM seconds |
|---|---|---|---|
| intake | 6 | 5,256 | 0.0 |
| guard | 8 | 5,435 | 0.0 |
| generator | 4 | 3,110 | 0.0 |
| evalgen | 31 | 11,638 | 0.0 |
| judge_calibration | 23 | 9,324 | 0.0 |
| tournament | 99 | 79,568 | 0.0 |
| optimizer | 30 | 26,770 | 0.0 |
| final_eval | 26 | 22,029 | 0.0 |
| report | 2 | 1,285 | 6.56 |

## Known limitations of this report

- The eval set is generated by the same family of small model that builds the agent; it inherits that model's blind spots. Key facts are verified to exist in the source, but question *quality* is not.
- Fact matching is lexical + LLM; correct answers phrased very differently can be scored as misses (see judge disagreements).
- Out-of-scope 'adjacent' questions are verified unanswerable by a second model, which can itself be wrong.
- Scores come from a single run at near-zero temperature; small differences (±1 case) are within noise.
