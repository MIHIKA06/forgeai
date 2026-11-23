"""Unit tests for the deterministic 'lie detectors' - no LLM needed."""
from forgeai import tools
from forgeai.judge import _corrupt
from forgeai.llm import extract_json
from forgeai.textutil import fact_in_text, looks_like_refusal, numbers, quote_in_text
from forgeai.generator import assemble, parse_sections, lint_sections, SECTIONS


def test_numbers_normalise():
    assert numbers("USD 1,320.00 and 24 days") >= {"1320", "24"}
    assert "5" in numbers("five working days")


def test_fact_requires_numbers():
    assert fact_in_text("24 working days of annual leave", "You get 24 working days of annual leave each year.")
    assert not fact_in_text("24 working days of annual leave", "You get 26 working days of annual leave each year.")


def test_quote_in_text_tolerates_pdf_noise():
    src = "Annual leave  accrues at the rate of 2 days for each\ncompleted month of service."
    assert quote_in_text("accrues at the rate of 2 days for each completed month", src)
    assert not quote_in_text("accrues at the rate of 3 days per week", src)


def test_refusal_detector():
    assert looks_like_refusal("I'm sorry, that is outside my scope. Please contact HR.")
    assert not looks_like_refusal("You are entitled to 12 days of sick leave.")


def test_extract_json_from_messy_output():
    assert extract_json('Sure! ```json\n{"a": 1,}\n```') == {"a": 1}
    assert extract_json('blah {"x": {"y": [1,2]}} trailing') == {"x": {"y": [1, 2]}}


def test_calculator_is_safe():
    assert tools.calculator("3 * 1,320.00")["result"] == 3960.0
    assert "error" in tools.calculator("__import__('os').system('ls')")


def test_corrupt_changes_meaning():
    assert _corrupt("12 days of sick leave") != "12 days of sick leave"
    assert "not" in _corrupt("leave is paid")


def test_prompt_sections_roundtrip_and_lint():
    sec = {k: f"text {k}" for k in SECTIONS}
    assert parse_sections(assemble(sec)) == sec
    req = {"must_refuse_topics": ["legal advice"], "known_gaps": ["payroll dates"]}
    fixed, notes = lint_sections(dict(sec), req, [])
    assert "legal advice" in fixed["refusal_policy"] and "payroll dates" in fixed["refusal_policy"]
    assert "only" in fixed["grounding_rules"].lower()


def test_csv_lookup(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("part_no,description,unit_price_usd\nA-1,Fire pump seal,780.00\nB-2,Boiler nozzle,260.00\n")
    tools.set_csv_files([str(p)])
    r = tools.csv_lookup("fire pump seal")
    assert r["rows"][0]["part_no"] == "A-1"
    assert tools.csv_lookup("B-2")["rows"][0]["unit_price_usd"] == "260.00"
