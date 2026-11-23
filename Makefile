PY ?= .venv/bin/python

setup:            ## create venv, install deps, pull open models
	uv venv --python 3.11 .venv && uv pip install --python $(PY) -r requirements.txt
	ollama pull qwen2.5:7b && ollama pull llama3.1:8b && ollama pull nomic-embed-text

data:             ## (re)render the synthetic demo corpora
	$(PY) demos/synthesize.py

test:             ## deterministic unit tests (no LLM)
	$(PY) -m pytest -q tests

demo-hr:          ## full factory run, demo 1
	$(PY) -m forgeai build --brief demos/hr_policy/brief.md --docs demos/hr_policy/docs --out runs/hr_policy

demo-spares:      ## full factory run, demo 2
	$(PY) -m forgeai build --brief demos/ship_spares/brief.md --docs demos/ship_spares/docs --out runs/ship_spares

baseline:         ## factory vs hand-written agent
	$(PY) -m forgeai baseline --run runs/hr_policy --agent baselines/hr_human_agent.json

regress:          ## documents changed -> old evals vs regenerated agent
	$(PY) -m forgeai regress --run runs/hr_policy --docs demos/hr_policy/docs_v2 --out runs/hr_policy_regression

ui:
	$(PY) -m streamlit run app.py
