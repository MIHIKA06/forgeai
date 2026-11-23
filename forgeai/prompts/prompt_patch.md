You are fixing ONE section of an assistant's system prompt. The assistant answers from retrieved document passages and runs on a small model, so rules must be short and concrete.

SECTION TO REWRITE: "{{section}}"
CURRENT TEXT OF THIS SECTION:
"""
{{current}}
"""

OTHER SECTIONS (for context, do not rewrite them):
"""
{{others}}
"""

FAILURE CATEGORY: {{category}}
DIAGNOSIS: {{diagnosis}}

FAILING EXAMPLES (from an evaluation run):
{{examples}}

Rewrite ONLY this section so that this class of failure stops happening. Rules:
- Fix the general behaviour; do NOT mention the specific example questions, answers, numbers or names (that would be overfitting to the test).
- Keep every existing rule that is still correct. Add at most 3 new lines.
- Maximum 140 words. Imperative bullet lines.

Return JSON: {"new_text": "...", "change_summary": "<one sentence: what you changed and why>"}
