# ForgeAI quality report — `HRAssistant`

> **Final agent v2: 20/25 eval cases pass (80%).** Dev split 88% → 88% over 2 optimisation iteration(s); untouched holdout split 62% → 62%.
> **Failure audit:** of 5 failures, an independent reviewer (judge model + source passages) attributes **3 to the agent**, **2 to flawed auto-generated tests or grading**, 0 unclear. The strict score above stands; if every suspected test error were excused it would be at most 88%. Both numbers are reported because the eval set is itself machine-generated.

## What still fails and why

The main weaknesses are in the model's ability to correctly identify out-of-scope questions and provide accurate, supported answers. The root causes are a lack of clear refusal policies and insufficient grounding rules. The next step is to implement a more robust refusal policy that explicitly states the model should refuse out-of-scope questions and only provide answers when all required facts are covered by the provided documents.

| Case | Type | Split | Category | Judge verdict | Deterministic evidence | Independent review | Root-cause hypothesis |
|---|---|---|---|---|---|---|---|
| M02 | multi_doc | dev | prompt_defect | missing expected facts ['Employees travel in economy class on all flights shorter than 6 hours.', 'The standard working  | fact score 0.0 | **test_error**: The assistant's answer is supported by passage S2, which states that core hours are 10:00 to 16:00 IST, and passage S1, which states that bu | Lack of clear refusal policies and insufficient grounding rules lead to the model providing answers without all required facts. |
| O04 | out_of_scope | dev | hallucination | answered a question it should have refused | answered instead of refusing; it cited ['leave_policy.pdf', 'workplace_policy.pdf'] - retrieved passages on a related topic (leave_policy.pdf, workpla | **agent_error**: reviewer said test_error ('The assistant's answer correctly states that personal medical information should not be st') - overruled: answere | Lack of clear refusal policies and insufficient grounding rules lead to the model answering out-of-scope questions. |
| A07 | answerable | holdout | hallucination | judge flagged unsupported claims: ['Anonymous reports of unethical behavior can also be made through the ethics hotline. | judge-flagged claims: ['Anonymous reports of unethical behavior can also be made through the ethics hotline.']; fact score 1.0 | **test_error**: The assistant's answer is fully supported by passage S1, which explicitly states that grievances may be escalated in writing to the HR Head  | Lack of clear refusal policies and insufficient grounding rules lead to the model making unsupported claims. |
| O01 | out_of_scope | holdout | hallucination | answered a question it should have refused | answered instead of refusing; it cited ['leave_policy.pdf'] - retrieved passages on a related topic (leave_policy.pdf, travel_expense_policy.pdf, work | **agent_error**: reviewer said test_error ('The assistant's answer correctly and fully answers the question from the passages, as it m') - overruled: answere | Lack of clear refusal policies and insufficient grounding rules lead to the model answering out-of-scope questions. |
| O05 | out_of_scope | holdout | hallucination | answered a question it should have refused | answered instead of refusing; it cited ['workplace_policy.pdf'] - retrieved passages on a related topic (leave_policy.pdf, workplace_policy.pdf) were  | **agent_error**: reviewer said test_error ('The assistant's answer is fully supported by passage S1, which directly addresses the poli') - overruled: answere | Lack of clear refusal policies and insufficient grounding rules lead to the model answering out-of-scope questions. |

<details><summary>Questions and answers of the failing cases</summary>

- **M02** Q: What are the travel class restrictions for employees in Mumbai and Chennai during core hours?  
  A: During core hours (10:00 to 16:00 IST), employees in Mumbai and Chennai must travel in economy class on all flights, regardless of duration. Business class is not restricted during these hours.
- **O04** Q: How do I handle an employee's personal medical information?  
  A: When handling an employee's personal medical information, ensure it is stored only on company-issued devices and never on personal devices or cloud accounts. Report any lost or stolen devices to the IT helpdesk within 24 hours. For medical certificates, obtain them from a registered medical practitioner as required for sick leave exceeding 2 consecutive days.
- **A07** Q: What is the process for resolving a grievance if it is not resolved by the manager?  
  A: If a grievance is not resolved by the reporting manager within 10 working days, it can be escalated in writing to the HR Head. Anonymous reports of unethical behavior can also be made through the ethics hotline.
- **O01** Q: Can you provide a disciplinary action procedure for the Mumbai office?  
  A: For unauthorised absence, the procedure involves absence exceeding 3 consecutive working days without approved leave. This is treated as unauthorised absence and may lead to disciplinary action under the Code of Conduct. Employees should ensure all leave is approved in advance.
- **O05** Q: What is the policy on hybrid work for the Mumbai office?  
  A: Eligible employees in the Mumbai office may work from home up to 2 days per week after completing their probation period. They must agree with their reporting manager and record this in the HRMS attendance module by Friday of the previous week. Home-office internet reimbursement is INR 1,000 per month, and the company provides a laptop and headset.

</details>

## Per-iteration scorecard (dev split — the only split the optimiser sees)

| Iter | Agent ver | Dev pass | Answer acc | Grounded | Refusal recall | False refusals | Retrieval hit | Failure categories | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| 0 | v0 | 15/17 (88%) | 92% | 100% | 80% | 0% | 100% | prompt_defect:1, hallucination:1 | baseline |
| 1 | v1 | 14/17 (82%) | 92% | 92% | 80% | 0% | 100% | hallucination:2, prompt_defect:1 | **reverted** |
| 2 | v2 | 15/17 (88%) | 92% | 100% | 80% | 0% | 100% | prompt_defect:1, hallucination:1 | accepted |

## Generalisation check (holdout split — never shown to the optimiser)

| Agent | Holdout pass | Answer acc | Grounded | Refusal recall | False refusals |
|---|---|---|---|---|---|
| v0 (before loop) | 5/8 (62%) | 100% | 80% | 33% | 0% |
| v2 (final) | 5/8 (62%) | 100% | 80% | 33% | 0% |

## Change log

### Iteration 1 — REVERTED (dev 88% → 82%)
Newly passing: – · Newly failing: ['M01']

- **prompt_defect → `prompt:answer_style`**: Added rules to ensure required facts and citations are included, and emphasized using only provided passages.
  - Why: The right passages were retrieved and the assistant answered, but the answer missed required facts, omitted citations, ignored an available tool, or broke the output format.
  - Addressed failures: ['M02'] · actually fixed: []

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -17,3 +17,3 @@
 ## Answer style
-Provide a short paragraph with a policy citation, followed by bullet steps for procedures. Quote exact figures when necessary. Keep sentences concise and to the point
+Provide concise paragraphs with policy citations, followed by bullet steps for procedures. Quote exact figures when necessary. Avoid missing required facts or omitting citations. Use only provided CONTEXT passages.
 
```
</details>

- **hallucination → `prompt:grounding_rules`**: Added refusal to answer out-of-scope questions and always citing used passages to prevent hallucination.
  - Why: The assistant stated things not supported by the passages, or answered questions that are out of scope instead of refusing.
  - Addressed failures: ['O04'] · actually fixed: []

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -10,3 +10,3 @@
 ## Grounding rules
-Use only provided CONTEXT passages; label references with [S1], [S2]...; do not invent facts, numbers, or policies; if passages conflict, state the conflict
+Use only provided CONTEXT passages; label references with [S1], [S2]...; do not invent facts, numbers, or policies; if passages conflict, state the conflict; refuse to answer questions outside scope; always cite passages used.
 
```
</details>

### Iteration 2 — accepted (dev 88% → 88%)
Newly passing: – · Newly failing: –

- **prompt_defect → `prompt:tool_use`**: Added rules for using tools and providing citations to ensure all required facts are included and the output format is maintained.
  - Why: The right passages were retrieved and the assistant answered, but the answer missed required facts, omitted citations, ignored an available tool, or broke the output format.
  - Addressed failures: ['M02'] · actually fixed: []

<details><summary>diff</summary>

```diff

```
</details>

- **hallucination → `prompt:refusal_policy`**: Clarified that refusal is the default action and only to escalate for uncovered topics, aligning with the refusal-first principle.
  - Why: The assistant stated things not supported by the passages, or answered questions that are out of scope instead of refusing.
  - Addressed failures: ['O04'] · actually fixed: []

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -13,4 +13,3 @@
 ## Refusal policy
-Refuse to discuss disciplinary actions, performance reviews, medical advice, legal advice, personal data, sensitive information, or individual employee cases. Escalate to the HR team for any uncovered topics
-- Always refuse: Salary structure; Payroll dates; Annual performance bonus.
+Refuse to discuss disciplinary actions, performance reviews, medical advice, legal advice, personal data, sensitive information, or individual employee cases. Escalate to the HR team for any uncovered topics. Always refuse: Salary structure; Payroll dates; Annual performance bonus.
 
```
</details>

_Stopped: early stop: two iterations without improvement (budget guard)_

_Loop stop reason: early stop: two iterations without improvement (budget guard)_

## Requirements & groundability guard

- **Purpose:** To provide HR policy information to shore staff in Mumbai and Chennai offices.
- **Audience:** Shore staff in Mumbai and Chennai offices
- **Approval:** auto-approved (unattended run)
- **Guard status:** `gaps_flagged` (topic coverage 62%)
  - ⚠️ Topic 'Salary structure' is not supported by the documents (What is the structure of salaries, including components like basic salary, HRA, and allowances?).
  - ⚠️ Topic 'Payroll dates' is not supported by the documents (When are payroll dates for encashing unused annual leave and final settlements?).
  - ⚠️ Topic 'Annual performance bonus' is not supported by the documents (What is the process for granting an annual performance bonus, and when is it typically awarded?).

## Tool selection

| Tool | Decision | Reason |
|---|---|---|
| csv_lookup | ❌ rejected | prerequisite failed: knowledge folder contains at least one CSV/TSV file; LLM wanted it but the requester's own words give no evidence for it (no signal words in brief/answers) |
| calculator | ❌ rejected | LLM wanted it but the requester's own words give no evidence for it (no signal words in brief/answers) |
| weather_forecast | ❌ rejected | not needed by any requirement |
| current_date | ❌ rejected | LLM wanted it but the requester's own words give no evidence for it (no signal words in brief/answers) |

## Prompt tournament

| Candidate | Dev pass | Mean fact score | Lint fixes | Result |
|---|---|---|---|---|
| A_strict | 15/17 | 0.917 | 1 | 🏆 winner |
| B_structured | 15/17 | 0.917 | 2 |  |

Tie-break (position-debiased pairwise judge): A_strict vs B_structured: {'A': 0, 'B': 0, 'tie': 6} (each pair judged in both orders; inconsistent verdicts count as tie)

## Eval set

25 generated cases: {'answerable': 12, 'ambiguous': 3, 'gap_probe': 3, 'multi_doc': 2, 'out_of_scope': 5} · splits {'holdout': 8, 'dev': 17}.
Generation audit (claims checked deterministically): {'multi_doc:dropped': 1, 'ambiguous:dropped': 1, 'out_of_scope:dropped': 1}.

## Judge calibration (planted canaries)

- Judge model `llama3.1:8b` vs agent model `qwen2.5:7b` → self-preference guard: different model family
- LLM judge accuracy on 20 canaries: 100% · deterministic checker: 90%
- Verbosity trap (long, fluent, wrong answers) caught: 100% · false-accept rate on corrupted answers: 0%
- Position consistency (fact order reversed): 100%
- Resulting judge mode: **full** — LLM may credit paraphrased facts the string matcher missed; numbers always checked deterministically
- Judge/deterministic disagreements during final eval: 14
- 'Unsupported claim' flags raised by the LLM judge but **overruled** because the claim is found verbatim-ish in the passages/question: 11 (observed failure mode of the 8B judge: it flags sentences copied from the passages; its groundedness veto is therefore only accepted when the deterministic checker agrees)

## Final agent definition

- Retrieval: `{"strategy": "section", "chunk_size": 120, "chunk_overlap": 20, "top_k": 5, "mode": "hybrid", "query_rewrite": false}`
- Output contract: JSON `{answer, citations, refused}`, max 120 words, citations required
- Prompt candidate: A_strict

<details><summary>System prompt</summary>

```
## Role
HRAssistant, providing HR policy information to shore staff in Mumbai and Chennai offices

## Audience & tone
Friendly but precise, avoiding legal advice or discussing individual cases

## Scope
Answers on leave policies, travel and expense claims, hybrid work rules, notice periods, and annual performance bonus calculations

## Grounding rules
Use only provided CONTEXT passages; label references with [S1], [S2]...; do not invent facts, numbers, or policies; if passages conflict, state the conflict

## Refusal policy
Refuse to discuss disciplinary actions, performance reviews, medical advice, legal advice, personal data, sensitive information, or individual employee cases. Escalate to the HR team for any uncovered topics. Always refuse: Salary structure; Payroll dates; Annual performance bonus.

## Answer style
Provide a short paragraph with a policy citation, followed by bullet steps for procedures. Quote exact figures when necessary. Keep sentences concise and to the point

## Tool use
No tools are available. Do not mention tools.
```
</details>

## Budget

- Tokens: 162,956 of 3,000,000 · LLM calls: 230 (cache hits 0) · wall time 60.9 min

| Stage | Calls | Tokens | LLM seconds |
|---|---|---|---|
| intake | 6 | 5,300 | 45.2 |
| guard | 8 | 5,444 | 25.56 |
| generator | 3 | 2,319 | 26.73 |
| evalgen | 32 | 11,979 | 193.41 |
| judge_calibration | 23 | 9,153 | 121.93 |
| tournament | 70 | 52,913 | 693.76 |
| optimizer | 62 | 53,014 | 5492.26 |
| final_eval | 26 | 22,834 | 167.81 |
| report | 6 | 5,304 | 33.57 |

## Known limitations of this report

- The eval set is generated by the same family of small model that builds the agent; it inherits that model's blind spots. Key facts are verified to exist in the source, but question *quality* is not.
- Fact matching is lexical + LLM; correct answers phrased very differently can be scored as misses (see judge disagreements).
- Out-of-scope 'adjacent' questions are verified unanswerable by a second model, which can itself be wrong.
- Scores come from a single run at near-zero temperature; small differences (±1 case) are within noise.
