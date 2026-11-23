List every distinct thing the requester explicitly asks the assistant to do or answer in this brief. Split combined asks ("salary structure, payroll dates and bonus") into separate items. Use short noun phrases. Do not add anything the brief does not say.

BRIEF:
"""
{{brief}}
"""

Return JSON: {"asks": ["..."]}
