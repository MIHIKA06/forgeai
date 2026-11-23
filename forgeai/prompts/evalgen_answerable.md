You write test questions for a QA engineer evaluating an assistant. The assistant serves: {{audience}}

Here is ONE passage from the document "{{doc}}":
"""
{{passage}}
"""

Write {{n}} realistic question(s) such a user would ask whose answer is stated in this passage. Rules:
- The question must NOT contain the answer.
- Do not mention the document name or "the passage".
- key_facts: 1-3 SHORT phrases (2-10 words) copied EXACTLY from the passage that a correct answer must state. Prefer specific numbers, durations, amounts, names, conditions.

Return JSON:
{"cases": [{"question": "...", "key_facts": ["exact phrase", "..."], "reference_answer": "<one sentence>"}]}
