You are a senior prompt engineer. Write the system prompt for an AI assistant that answers ONLY from retrieved document passages (it receives CONTEXT passages labelled [S1], [S2]... with each question). It runs on a small open model, so instructions must be short, concrete and unambiguous - no fluff.

REQUIREMENTS:
{{requirements}}

TOPICS THE DOCUMENTS DO NOT COVER (must be refused, never guessed): {{gaps}}
TOOLS ATTACHED: {{tools}}

STYLE FOR THIS CANDIDATE: {{style}}

Write each section as 2-6 short imperative sentences or bullet lines. Return JSON:
{"role": "<who the assistant is and for whom>",
 "audience_tone": "<how to talk to the audience>",
 "scope": "<what it answers>",
 "grounding_rules": "<how to use CONTEXT; cite labels; never invent facts, numbers or policies; if passages conflict, say so>",
 "refusal_policy": "<what to refuse and how; name the must-refuse topics and the uncovered topics; point to the escalation contact>",
 "answer_style": "<length, structure, how to state numbers/conditions/exceptions>",
 "tool_use": "<when to call each attached tool, or 'No tools are available.'>"}
