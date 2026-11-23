You write a hard test question that can only be answered by combining TWO documents. The assistant serves: {{audience}}

PASSAGE 1 (from "{{doc_a}}"):
"""
{{passage_a}}
"""

PASSAGE 2 (from "{{doc_b}}"):
"""
{{passage_b}}
"""

Write ONE natural question whose complete answer needs a fact from passage 1 AND a fact from passage 2. Do not mention documents or passages.
key_facts_1: 1-2 short phrases copied EXACTLY from passage 1. key_facts_2: 1-2 short phrases copied EXACTLY from passage 2.

Return JSON: {"question": "...", "key_facts_1": ["..."], "key_facts_2": ["..."], "reference_answer": "..."}
If no sensible combined question exists, return {"question": ""}.
