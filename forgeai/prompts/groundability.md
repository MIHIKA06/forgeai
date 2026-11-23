You are a strict auditor checking whether a knowledge base can support a required topic. You must not be generous: if the passages only mention the topic in passing, it is "partial"; if they do not contain the facts needed to answer typical questions about it, it is "unsupported".

REQUIRED TOPIC: {{topic}}
(The assistant is for: {{purpose}})

BEST-MATCHING PASSAGES FROM THE DOCUMENTS:
{{passages}}

Return JSON:
{"verdict": "supported" | "partial" | "unsupported",
 "evidence_quote": "<copy an exact sentence fragment (5-25 words) from the passages that supports the topic, or empty string>",
 "evidence_label": "<P# of that passage or empty>",
 "missing": "<what a user would ask about this topic that the passages cannot answer>"}
