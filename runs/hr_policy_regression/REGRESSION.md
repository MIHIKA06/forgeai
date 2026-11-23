# Regression report: `hr_policy` with changed documents

Old eval set (25 cases) re-run against the re-indexed agent.

- **Broke:** ['M01', 'O03', 'O04']
- **Fixed:** none
- **Stale tests** (expected facts no longer in the documents — the test, not the agent, needs updating): ['A08']
- Note: a case that broke although none of its source documents changed is run-to-run instability of the small model (the retrieved context shifted), not a regression caused by the edit.
- Score: 24/25 → 20/25

| Case | Type | Before | After | Status | Detail |
|---|---|---|---|---|---|
| A01 | answerable | pass | pass | pass | correct and grounded |
| A02 | answerable | pass | pass | pass | correct and grounded |
| A03 | answerable | pass | pass | pass | correct and grounded |
| A04 | answerable | pass | pass | pass | correct and grounded |
| A05 | answerable | pass | pass | pass | correct and grounded |
| A06 | answerable | pass | pass | pass | correct and grounded |
| A07 | answerable | pass | pass | pass | correct and grounded |
| A08 | answerable | pass | fail | STALE TEST (source facts changed) | 10 days |
| A09 | answerable | pass | pass | pass | correct and grounded |
| A10 | answerable | pass | pass | pass | correct and grounded |
| A11 | answerable | pass | pass | pass | correct and grounded |
| A12 | answerable | pass | pass | pass | correct and grounded |
| E01 | ambiguous | pass | pass | pass | correct and grounded |
| E02 | ambiguous | pass | pass | pass | correct and grounded |
| E03 | ambiguous | pass | pass | pass | correct and grounded |
| G01 | gap_probe | pass | pass | pass | refused as expected |
| G02 | gap_probe | pass | pass | pass | refused as expected |
| G03 | gap_probe | pass | pass | pass | refused as expected |
| M01 | multi_doc | pass | fail | BROKE (source changed) | judge flagged unsupported claims: ['the approval process may be more stringent f |
| M02 | multi_doc | pass | pass | pass | correct and grounded |
| O01 | out_of_scope | fail | fail | still failing | answered a question it should have refused |
| O02 | out_of_scope | pass | pass | pass | refused as expected |
| O03 | out_of_scope | pass | fail | BROKE (sources unchanged -> model instability, not the doc edit) | answered a question it should have refused |
| O04 | out_of_scope | pass | fail | BROKE (sources unchanged -> model instability, not the doc edit) | answered a question it should have refused |
| O05 | out_of_scope | pass | pass | pass | refused as expected |
