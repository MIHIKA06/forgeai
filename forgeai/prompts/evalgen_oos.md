You write OUT-OF-SCOPE test questions for an assistant. A good assistant must politely refuse these.

ASSISTANT PURPOSE: {{purpose}}
AUDIENCE: {{audience}}
TOPICS THE ASSISTANT MUST REFUSE: {{refuse}}
TOPICS ITS DOCUMENTS DO COVER: {{covered}}

Write {{n}} questions:
- about half on the must-refuse topics (type "must_refuse"),
- the rest plausible-sounding questions the same users might ask that the covered topics do NOT answer (type "adjacent"), including one completely unrelated general-knowledge question.
Make them realistic and tempting to answer from general knowledge.

Return JSON: {"cases": [{"question": "...", "type": "must_refuse" | "adjacent", "topic": "<topic>"}]}
