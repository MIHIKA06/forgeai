You write the structured requirements document for an AI assistant that will be generated automatically.

BRIEF:
"""
{{brief}}
"""

DOCUMENT INVENTORY (the ONLY knowledge the assistant will have):
{{inventory}}

CLARIFICATIONS (answers from the requester, or default assumptions):
{{clarifications}}

Rules:
- must_answer_topics: 5-10 concrete topics the assistant must handle, phrased as short noun phrases. Include topics the brief asks for EVEN IF the documents may not cover them (a separate checker verifies coverage).
- must_refuse_topics: 3-8 topics the assistant must decline (out of scope, sensitive, legal/medical advice, personal data, anything the requester excluded).
- capabilities_needed: actions beyond reading documents that the brief implies, e.g. "arithmetic on prices", "today's date for deadlines", "exact lookup in a catalogue table", "live weather". Use [] if none. Do not invent needs the brief does not imply.
- tone: one sentence. audience: one sentence.

Return JSON:
{"agent_name": "<short PascalCase or kebab name>",
 "purpose": "<one sentence>",
 "audience": "...",
 "tone": "...",
 "scope": "<2-3 sentences of what is in scope>",
 "must_answer_topics": ["..."],
 "must_refuse_topics": ["..."],
 "capabilities_needed": ["..."],
 "answer_format": "<e.g. short paragraph with policy citation; bullet steps for procedures>",
 "escalation_contact": "<who to send users to when refusing, or 'the responsible team'>"}
