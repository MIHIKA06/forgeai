You are cataloguing a knowledge document for an AI-agent factory.

Document file: {{name}}
Section headings found: {{headings}}

Document text (may be truncated):
"""
{{text}}
"""

Return JSON:
{"summary": "<2 sentences: what this document is and who it is for>",
 "topics": ["<8-15 short topic phrases that this document can actually answer questions about>"],
 "doc_type": "<policy | catalogue | manual | contract | faq | report | other>"}
Only list topics that are explicitly covered by the text.
