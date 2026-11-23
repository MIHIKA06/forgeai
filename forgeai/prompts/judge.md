You are grading ONE answer from an assistant against a checklist of expected facts. Judge each fact independently.
Length, tone, politeness and confidence are IRRELEVANT - a short answer that states a fact counts the same as a long one; extra words never earn credit.

QUESTION: {{question}}

EXPECTED FACTS:
{{facts}}

PASSAGES THE ASSISTANT WAS GIVEN:
{{passages}}

ASSISTANT ANSWER:
"""
{{answer}}
"""

For each expected fact decide:
- "stated": the answer states this fact (paraphrase is fine, numbers must match exactly)
- "contradicted": the answer states something incompatible with it
- "missing": the answer does not state it
Then list any claims in the answer that are NOT supported by the passages (numbers, rules, names that do not appear there).

Return JSON:
{"facts": [{"id": 1, "verdict": "stated" | "contradicted" | "missing"}],
 "unsupported_claims": ["..."],
 "grounded": true | false}
