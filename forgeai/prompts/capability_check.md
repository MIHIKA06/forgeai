An assistant is being built. Its requirements list capabilities beyond reading documents. Decide, for each capability, what can satisfy it.

AVAILABLE TOOLS:
{{tools}}

KNOWLEDGE FILES: {{files}}

CAPABILITIES NEEDED:
{{capabilities}}

For each capability choose exactly one:
- "documents"  : answering from the knowledge files alone is enough
- "<tool name>": one of the tools above provides it
- "unsupported": nothing available can do it (e.g. live data feeds, writing to other systems, submitting requests, personal records not in the files)

Return JSON: {"mapping": [{"capability": "...", "satisfied_by": "...", "reason": "<one short sentence>"}]}
