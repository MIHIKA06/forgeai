Two assistants answered the same question. Decide which answer is better at stating the expected facts correctly, grounded in the documents, without unsupported claims. Length is irrelevant: do not prefer the longer answer.

QUESTION: {{question}}
EXPECTED FACTS: {{facts}}

ANSWER X:
"""
{{a}}
"""

ANSWER Y:
"""
{{b}}
"""

Return JSON: {"winner": "X" | "Y" | "tie", "reason": "<one sentence>"}
