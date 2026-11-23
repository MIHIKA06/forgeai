You are writing the "what still fails and why" section of an honest QA report about an auto-generated document assistant. Be specific and candid. Base every claim on the evidence given; do not invent causes.

Rules:
- Do NOT recommend retraining or fine-tuning the model. Recommend concrete actions: edit a prompt section, change retrieval, add/clarify a document, or fix/remove a flawed TEST CASE.
- Auto-generated tests can be wrong. If a question does not actually require its expected facts, or a refusal test asks about something the documents arguably cover, say the test is questionable.
- Name the case ids.

REMAINING FAILURES (with judge verdict and deterministic evidence):
{{failures}}

FIXES ALREADY TRIED BY THE OPTIMISER:
{{fixes}}

Return JSON: {"summary": "<3-6 sentences: the main remaining weaknesses, their evidenced root causes, and the next concrete step for a human engineer>",
 "per_case": [{"id": "<case id>", "why": "<one sentence root-cause hypothesis>"}]}
