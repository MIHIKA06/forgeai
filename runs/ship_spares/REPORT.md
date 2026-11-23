# ForgeAI quality report — `SparePartAssistant`

> **Final agent v2: 19/27 eval cases pass (70%).** Dev split 74% → 74% over 2 optimisation iteration(s); untouched holdout split 38% → 62%.
> **Failure audit:** of 8 failures, an independent reviewer (judge model + source passages) attributes **3 to the agent**, **5 to flawed auto-generated tests or grading**, 0 unclear. The strict score above stands; if every suspected test error were excused it would be at most 89%. Both numbers are reported because the eval set is itself machine-generated.

## What still fails and why

The main remaining weaknesses are in prompt formulation and the model's ability to correctly identify and use tools for calculations. The root causes are prompt defects and hallucinations. The next step is to refine the prompt templates to ensure they include all necessary facts and instructions for tool use, and to implement stricter checks for numerical accuracy.

| Case | Type | Split | Category | Judge verdict | Deterministic evidence | Independent review | Root-cause hypothesis |
|---|---|---|---|---|---|---|---|
| A06 | answerable | dev | prompt_defect | missing expected facts ['Above USD 2,000 and up to USD 10,000'] | fact score 0.5 | **test_error**: The passages state that technical superintendent approval is required for purchase orders above USD 2,000, which includes orders valued at $ | Prompt defect, leading to missing expected facts. |
| A10 | answerable | dev | hallucination | did not cite the expected source; judge flagged unsupported claims: ['The warranty period varies between suppliers.'] | judge-flagged claims: ['The warranty period varies between suppliers.']; fact score 1.0; expected source not cited; contract: ['output was not valid c | **test_error**: The assistant's answer correctly states that the warranty period varies between suppliers and provides specific information from passages S1 | Hallucination, leading to unsupported claims and missing expected facts. |
| E03 | ambiguous | dev | hallucination | judge flagged unsupported claims: ['For such urgent orders, you can place an emergency purchase by phone or email and re | judge-flagged claims: ['For such urgent orders, you can place an emergency purchase by phone or email and regularize it in the system within 2 working | **test_error**: The assistant's answer is fully supported by passage S1, which explicitly states that air freight is permitted for emergency purchases or cr | Hallucination, leading to unsupported claims and missing expected facts. |
| M01 | multi_doc | dev | wrong_refusal | refused although the answer is in the documents | source WAS retrieved (['procurement_policy.pdf', 'spares_catalogue.csv', 'supplier_oceanic_terms.pdf']) but the model refused | **agent_error**: reviewer said test_error ('The assistant's answer is correct as it states that the answer cannot be determined from t') - overruled: refused | Refusal policy issue, leading to wrong refusal despite available information. |
| T03 | tool | dev | prompt_defect | missing expected facts ['582']; expected tool calculator was not called | fact score 0.0 | **agent_error**: reviewer said test_error ('The expected fact '582' is not present in the passages, and the question asks for the tota') - overruled: tool ca | Prompt defect, leading to missing expected facts and tool use issues. |
| A05 | answerable | holdout | prompt_defect | missing expected facts ['48 hours'] | fact score 0.5 | **test_error**: The passage [S1] explicitly states that for criticality A items, Oceanic offers urgent dispatch within 48 hours of order confirmation, for a | Prompt defect, leading to missing expected facts. |
| A07 | answerable | holdout | wrong_refusal | refused although the answer is in the documents | source WAS retrieved (['procurement_policy.pdf', 'supplier_marinetech_terms.pdf', 'supplier_oceanic_terms.pdf']) but the model refused | **agent_error**: reviewer said test_error ('The passages do not specify a specific charge for delivery to ports other than Singapore o') - overruled: refused | Prompt defect, leading to wrong refusal and missing expected facts. |
| T02 | tool | holdout | hallucination | numbers not found in any passage/tool output: ['44200']; expected tool calculator was not called | numbers absent from every passage: ['44200']; fact score 1.0 | **test_error**: The expected fact '44200' was not found in the passage S1, which actually states the unit price as $4420.00. | Tool defect, leading to incorrect numerical results and hallucination. |

<details><summary>Questions and answers of the failing cases</summary>

- **A06** Q: What approval is needed for a purchase order valued at $7,500?  
  A: For a purchase order valued at $7,500, technical superintendent approval is needed.
- **A10** Q: What is the warranty period for parts based on the date of delivery or installation?  
  A: The warranty period varies between suppliers. MarineTech offers a 12 months warranty from the date of delivery or 6 months from installation, whichever comes first. Oceanic provides an 18-month warranty from the date of delivery.
- **E03** Q: Can we use air freight for urgent orders or crit A stuff? What if we need it in <10 days?  
  A: Air freight is permitted for emergency purchases or criticality A items with a required-by date less than 10 days away. For such urgent orders, you can place an emergency purchase by phone or email and regularize it in the system within 2 working days.
- **M01** Q: What approval is needed for an order of turbocharger parts worth $12,000?  
  A: I can't answer that from the documents I have access to. Please contact the responsible team.
- **T03** Q: What is the total unit price in USD for buying 12 units of the Atlas Copco Service air compressor filter element with part number MT-CMP-2004?  
  A: The total unit price in USD for buying 12 units of the Atlas Copco Service air compressor filter element with part number MT-CMP-2004 is $48.50.
- **A05** Q: What is the surcharge for urgent dispatch of criticality A items?  
  A: The surcharge for urgent dispatch of criticality A items is 20 percent of the order value.
- **A07** Q: What additional charge is applied for delivery to ports other than Singapore or Rotterdam?  
  A: I can't answer that from the documents I have access to. Please contact the responsible team.
- **T02** Q: What is the total unit price in USD for purchasing 10 units of the Main engine fuel pump plunger and barrel with part number OE-ME-7006 from Oceanic Engine Parts?  
  A: The total unit price in USD for purchasing 10 units of the Main engine fuel pump plunger and barrel with part number OE-ME-7006 from Oceanic Engine Parts is $44,200.00.

</details>

## Per-iteration scorecard (dev split — the only split the optimiser sees)

| Iter | Agent ver | Dev pass | Answer acc | Grounded | Refusal recall | False refusals | Retrieval hit | Failure categories | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| 0 | v0 | 14/19 (74%) | 79% | 85% | 100% | 7% | 100% | prompt_defect:3, hallucination:1, wrong_refusal:1 | baseline |
| 1 | v1 | 12/19 (63%) | 79% | 69% | 100% | 7% | 100% | prompt_defect:3, hallucination:3, wrong_refusal:1 | **reverted** |
| 2 | v2 | 14/19 (74%) | 79% | 85% | 100% | 7% | 100% | prompt_defect:2, hallucination:2, wrong_refusal:1 | accepted |

## Generalisation check (holdout split — never shown to the optimiser)

| Agent | Holdout pass | Answer acc | Grounded | Refusal recall | False refusals |
|---|---|---|---|---|---|
| v0 (before loop) | 3/8 (38%) | 67% | 40% | 100% | 17% |
| v2 (final) | 5/8 (62%) | 67% | 80% | 100% | 17% |

## Change log

### Iteration 1 — REVERTED (dev 74% → 63%)
Newly passing: ['A11'] · Newly failing: ['A09', 'A12', 'E03']

- **prompt_defect → `prompt:tool_use`**: Added a rule to ensure all answers include necessary facts and cite sources as required to address the failure category.
  - Why: The right passages were retrieved and the assistant answered, but the answer missed required facts, omitted citations, ignored an available tool, or broke the output format.
  - Addressed failures: ['A06', 'A11', 'T03'] · actually fixed: ['A11']

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -21 +21,2 @@
 - calculator: The agent must compute numbers (totals, discounts, pro-rata entitlements, conversions).
+- Ensure all answers include necessary facts and cite sources as required.
```
</details>

- **hallucination → `prompt:grounding_rules`**: Added rules to refuse out-of-scope questions and cite sources, addressing the hallucination issue.
  - Why: The assistant stated things not supported by the passages, or answered questions that are out of scope instead of refusing.
  - Addressed failures: ['A10'] · actually fixed: []

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -10,3 +10,3 @@
 ## Grounding rules
-[S1] Use only the provided CONTEXT passages. [S2] Never invent facts, numbers, or policies. [S3] If passages conflict, state the conflict clearly.
+[S1] Use only the provided CONTEXT passages. [S2] Never invent facts, numbers, or policies. [S3] If passages conflict, state the conflict clearly. [S4] Refuse to answer questions outside the scope of spare parts procurement. [S5] Always cite sources when quoting exact figures.
 
```
</details>

### Iteration 2 — accepted (dev 74% → 74%)
Newly passing: ['A11'] · Newly failing: ['E03']

- **prompt_defect → `prompt:answer_style`**: Added tool usage and source citation to ensure all required facts are included.
  - Why: The right passages were retrieved and the assistant answered, but the answer missed required facts, omitted citations, ignored an available tool, or broke the output format.
  - Addressed failures: ['A06', 'A11', 'T03'] · actually fixed: ['A11']

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -16,3 +16,3 @@
 ## Answer style
-Provide answers in 1-2 sentences, then key conditions or exceptions. Quote exact figures from the passages when applicable.
+Provide answers in 1-2 sentences, then key conditions or exceptions. Quote exact figures from the passages when applicable. Always use the available tools for calculations. Cite the source of quoted figures.
 
```
</details>

- **hallucination → `prompt:refusal_policy`**: Added refusal of information not supported by context and questions outside the scope to prevent hallucination.
  - Why: The assistant stated things not supported by the passages, or answered questions that are out of scope instead of refusing.
  - Addressed failures: ['A10'] · actually fixed: []

<details><summary>diff</summary>

```diff
--- before
+++ after
@@ -13,3 +13,3 @@
 ## Refusal policy
-Refuse topics: Legal Advice, Personal Data, Sensitive Information, Detailed Policy Explanations, Escalation Procedures, Supplier Prioritization, Multiple Supplier Tracking. Must refuse: track the status of orders, Live Stock Levels. Escalate to the responsible team.
+Refuse topics: Legal Advice, Personal Data, Sensitive Information, Detailed Policy Explanations, Escalation Procedures, Supplier Prioritization, Multiple Supplier Tracking. Must refuse: track the status of orders, Live Stock Levels. Do not provide information not supported by context. Refuse questions outside the scope of spare parts procurement.
 
```
</details>

_Stopped: early stop: two iterations without improvement (budget guard)_

_Loop stop reason: early stop: two iterations without improvement (budget guard)_

## Requirements & groundability guard

- **Purpose:** To assist chief engineers and technical superintendents in managing ship spare-parts procurement.
- **Audience:** Chief engineers and technical superintendents, often on board with slow internet.
- **Approval:** auto-approved (unattended run)
- **Guard status:** `gaps_flagged` (topic coverage 90%)
  - ⚠️ Topic 'track the status of orders' is not supported by the documents (How to track the status of orders once they are placed?).
  - ⚠️ Capability 'Live Stock Levels' cannot be provided by documents or tools (No tool or document supports live stock level information.).

## Tool selection

| Tool | Decision | Reason |
|---|---|---|
| csv_lookup | ✅ attached | Allows precise lookups in the structured spares catalogue. |
| calculator | ✅ attached | Needed for computing totals and discounts. |
| weather_forecast | ❌ rejected | not needed by any requirement |
| current_date | ❌ rejected | LLM wanted it but the requester's own words give no evidence for it (no signal words in brief/answers) |

## Prompt tournament

| Candidate | Dev pass | Mean fact score | Lint fixes | Result |
|---|---|---|---|---|
| A_strict | 14/19 | 0.786 | 3 | 🏆 winner |
| B_structured | 13/19 | 0.821 | 4 |  |
| C_cautious | 14/19 | 0.75 | 4 |  |

Tie-break (position-debiased pairwise judge): A_strict vs C_cautious: {'A': 1, 'B': 0, 'tie': 5} (each pair judged in both orders; inconsistent verdicts count as tie)

## Eval set

27 generated cases: {'answerable': 12, 'ambiguous': 3, 'gap_probe': 2, 'multi_doc': 2, 'out_of_scope': 5, 'tool': 3} · splits {'holdout': 8, 'dev': 19}.
Generation audit (claims checked deterministically): {'multi_doc:dropped': 1, 'tool:dropped': 1}.

## Judge calibration (planted canaries)

- Judge model `llama3.1:8b` vs agent model `qwen2.5:7b` → self-preference guard: different model family
- LLM judge accuracy on 20 canaries: 100% · deterministic checker: 90%
- Verbosity trap (long, fluent, wrong answers) caught: 100% · false-accept rate on corrupted answers: 0%
- Position consistency (fact order reversed): 100%
- Resulting judge mode: **full** — LLM may credit paraphrased facts the string matcher missed; numbers always checked deterministically
- Judge/deterministic disagreements during final eval: 18
- 'Unsupported claim' flags raised by the LLM judge but **overruled** because the claim is found verbatim-ish in the passages/question: 9 (observed failure mode of the 8B judge: it flags sentences copied from the passages; its groundedness veto is therefore only accepted when the deterministic checker agrees)

## Final agent definition

- Retrieval: `{"strategy": "section", "chunk_size": 120, "chunk_overlap": 20, "top_k": 6, "mode": "hybrid", "query_rewrite": false}`
- Output contract: JSON `{answer, citations, refused}`, max 120 words, citations required
- Prompt candidate: A_strict

<details><summary>System prompt</summary>

```
## Role
SparePartAssistant, assisting chief engineers and technical superintendents

## Audience & tone
Practical and concise, providing quick answers

## Scope
Handling inquiries related to spare parts procurement, including price, lead time, supplier terms, and order tracking

## Grounding rules
[S1] Use only the provided CONTEXT passages. [S2] Never invent facts, numbers, or policies. [S3] If passages conflict, state the conflict clearly.

## Refusal policy
Refuse topics: Legal Advice, Personal Data, Sensitive Information, Detailed Policy Explanations, Escalation Procedures, Supplier Prioritization, Multiple Supplier Tracking. Must refuse: track the status of orders, Live Stock Levels. Do not provide information not supported by context. Refuse questions outside the scope of spare parts procurement.

## Answer style
Provide answers in 1-2 sentences, then key conditions or exceptions. Quote exact figures from the passages when applicable. Always use the available tools for calculations. Cite the source of quoted figures.

## Tool use
- csv_lookup: Precise lookups in structured catalogues/tables (prices, codes, quantities, lead times).
- calculator: The agent must compute numbers (totals, discounts, pro-rata entitlements, conversions).
```
</details>

## Budget

- Tokens: 255,630 of 3,000,000 · LLM calls: 314 (cache hits 314) · wall time 0.0 min

| Stage | Calls | Tokens | LLM seconds |
|---|---|---|---|
| intake | 7 | 5,962 | 0.0 |
| guard | 11 | 7,127 | 0.0 |
| generator | 4 | 3,431 | 0.0 |
| evalgen | 35 | 13,104 | 0.0 |
| judge_calibration | 24 | 10,477 | 0.0 |
| tournament | 119 | 109,627 | 0.0 |
| optimizer | 84 | 76,255 | 0.0 |
| final_eval | 30 | 29,647 | 0.0 |
| report | 9 | 8,676 | 27.9 |

## Known limitations of this report

- The eval set is generated by the same family of small model that builds the agent; it inherits that model's blind spots. Key facts are verified to exist in the source, but question *quality* is not.
- Fact matching is lexical + LLM; correct answers phrased very differently can be scored as misses (see judge disagreements).
- Out-of-scope 'adjacent' questions are verified unanswerable by a second model, which can itself be wrong.
- Scores come from a single run at near-zero temperature; small differences (±1 case) are within noise.
