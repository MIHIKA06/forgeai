# Factory vs human baseline

Same 25 generated eval cases, same judge (mode: full).

| Metric | Factory | Human |
|---|---|---|
| pass_rate | 0.96 | 0.92 |
| answer_accuracy | 1.0 | 0.941 |
| groundedness | 1.0 | 0.941 |
| refusal_recall | 0.875 | 0.875 |
| false_refusal_rate | 0.0 | 0.0 |
| contract_violation_rate | 0.0 | 0.0 |

| By type | Factory | Human |
|---|---|---|
| ambiguous | 3/3 | 3/3 |
| answerable | 12/12 | 12/12 |
| gap_probe | 3/3 | 3/3 |
| multi_doc | 2/2 | 1/2 |
| out_of_scope | 4/5 | 4/5 |

## Cases where they differ

| Case | Type | Factory | Human | Why (loser's judge evidence) |
|---|---|---|---|---|
| M01 | multi_doc | ✅ | ❌ | missing expected facts ['Domestic travel is approved by the reporting manager.', 'International travel require |
| O01 | out_of_scope | ❌ | ✅ | answered a question it should have refused |
| O04 | out_of_scope | ✅ | ❌ | answered a question it should have refused |
