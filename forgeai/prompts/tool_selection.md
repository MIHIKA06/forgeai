You select tools for an AI assistant. Attaching an unnecessary tool is a DEFECT (e.g. a weather tool on an HR assistant). Attach a tool only if typical users of this assistant will clearly need it.

REQUIREMENTS:
{{requirements}}

KNOWLEDGE FILES: {{files}}

TOOL REGISTRY:
{{tools}}

For EVERY tool in the registry decide attach true/false. If attach is true you must give "evidence": a short phrase copied exactly from the REQUIREMENTS text above that shows the need.

Return JSON:
{"decisions": [{"tool": "<name>", "attach": true|false, "evidence": "<exact phrase from requirements or empty>", "reason": "<one sentence>"}]}
