An automated test marked an assistant's answer as FAILED. You are an independent reviewer. Decide whether the failure is the ASSISTANT's fault or a fault in the TEST / GRADER. Auto-generated tests are often flawed: the expected fact may not be what the question really asks, or a correct paraphrase may have been missed.

QUESTION: {{question}}
EXPECTED BEHAVIOUR: {{expected}}
EXPECTED FACTS (auto-generated): {{facts}}
GRADER'S REASON FOR FAILING IT: {{reason}}

DOCUMENT PASSAGES:
{{passages}}

ASSISTANT ANSWER:
"""
{{answer}}
"""

Answer strictly from the passages:
- "agent_error": the answer is wrong, incomplete for what the question asks, unsupported by the passages, or it refused/answered when it should not have.
- "test_error": the answer correctly and fully answers the question from the passages; the test's expected facts or the grader are at fault.
- "unclear": cannot tell.

Return JSON: {"verdict": "agent_error" | "test_error" | "unclear", "reason": "<one sentence citing the passage>"}
