"""Stage 5 - the judge. Hybrid: deterministic checks are primary, an LLM judge of a DIFFERENT
model family adds semantic matching. Defences against known LLM-judge failure modes:

* verbosity bias   - decomposed per-fact binary verdicts instead of a holistic score; prompt says
                     length is irrelevant; measured with verbose-but-wrong canaries.
* position bias    - per-fact verdicts are re-asked with the fact order reversed on canaries;
                     pairwise comparisons are always run in both orders, inconsistent = tie.
* self-preference  - judge model != agent model (different family) by default.
* number laundering- the LLM can never mark a fact 'stated' if the fact's numbers are absent.
* calibration      - planted canaries (gold / corrupted / verbose-wrong / terse-correct) measure the
                     judge's accuracy every run; if it is unreliable it is demoted to advisory.
"""
from __future__ import annotations

import random
import re
from typing import Optional

from . import llm
from .config import SETTINGS
from .textutil import fact_in_text, looks_like_refusal, numbers


class Judge:
    def __init__(self, model: Optional[str] = None, use_llm: bool = True):
        self.model = model or SETTINGS.judge_model
        self.use_llm = use_llm
        self.llm_mode = "full"  # full | advisory | off
        self.calibration: dict = {}

    # ------------------------------------------------------------------ raw LLM call
    def _llm_facts(self, question: str, facts: list[str], passages: str, answer: str) -> Optional[dict]:
        if not self.use_llm or self.llm_mode == "off" or not facts:
            return None
        ftxt = "\n".join(f"{i+1}. {f}" for i, f in enumerate(facts))
        try:
            r = llm.chat_json(llm.render("judge", question=question, facts=ftxt, passages=passages[:5000], answer=answer[:2500]),
                              validate=llm.require_keys("facts"), model=self.model, max_tokens=500)
        except Exception:
            return None
        verdicts = ["missing"] * len(facts)
        for item in r.get("facts", []):
            try:
                i = int(item.get("id")) - 1
                v = str(item.get("verdict", "missing")).lower()
                if 0 <= i < len(facts) and v in ("stated", "contradicted", "missing"):
                    verdicts[i] = v
            except Exception:
                continue
        return {"verdicts": verdicts, "unsupported_claims": [str(x) for x in r.get("unsupported_claims", []) if str(x).strip()][:5],
                "grounded": bool(r.get("grounded", True))}

    # ------------------------------------------------------------------ per case
    def judge(self, case: dict, resp: dict) -> dict:
        answer = resp.get("answer", "")
        refused = bool(resp.get("refused")) or (looks_like_refusal(answer) and not resp.get("citations"))
        retrieved_docs = {p["doc"] for p in resp.get("passages", [])}
        tool_used = {t["tool"] for t in resp.get("tool_results", [])}
        evidence = " ".join(p["text"] for p in resp.get("passages", [])) + " " + " ".join(str(t["result"]) for t in resp.get("tool_results", []))
        v = {"id": case["id"], "type": case["type"], "split": case.get("split", "dev"), "question": case["question"],
             "expected_behavior": case["expected_behavior"], "answer": answer, "refused": refused,
             "cited_docs": resp.get("cited_docs", []), "retrieved_docs": sorted(retrieved_docs), "tools_called": sorted(tool_used),
             "contract_violations": resp.get("contract_violations", []), "latency_s": resp.get("latency_s"), "tokens": resp.get("tokens")}

        if case["expected_behavior"] == "refuse":
            v.update(passed=refused, correct=refused, grounded=None, fact_score=None,
                     reason="refused as expected" if refused else "answered a question it should have refused")
            v["category"] = None if refused else "hallucination"
            return v

        # ---- answerable
        exp = set(case.get("expected_sources", []))
        hit = bool(exp & retrieved_docs) or (case.get("requires_tool") in tool_used if case.get("requires_tool") else False)
        if case["type"] == "multi_doc":
            hit = exp <= retrieved_docs
        v["retrieval_hit"] = hit
        if refused:
            v.update(passed=False, correct=False, grounded=None, fact_score=0.0,
                     reason="refused although the answer is in the documents" + ("" if hit else " (and retrieval missed the source)"))
            v["category"] = "wrong_refusal" if hit else "retrieval_miss"
            return v

        facts = case.get("key_facts", [])
        det = [fact_in_text(f, answer, 0.7) for f in facts]
        lj = self._llm_facts(case["question"], facts, "\n\n".join(f"[{p['label']}] {p['text']}" for p in resp.get("passages", [])), answer)
        final, disagreements = [], 0
        for i, f in enumerate(facts):
            ok = det[i]
            if lj:
                lv = lj["verdicts"][i]
                llm_ok = lv == "stated" and numbers(f) <= numbers(answer)
                if llm_ok != det[i]:
                    disagreements += 1
                if self.llm_mode == "full" and llm_ok and not det[i]:
                    ok = True  # semantic paraphrase the string matcher missed
                if lv == "contradicted" and det[i] and not numbers(f):
                    ok = False  # word overlap but meaning reversed (e.g. 'not eligible')
            final.append(ok)
        fact_score = sum(final) / len(final) if final else 0.0
        threshold = 0.5 if case["type"] == "multi_doc" or len(facts) >= 3 else 0.6
        correct = fact_score >= threshold

        # Distrust the judge's groundedness veto: a claim it calls 'unsupported' only counts if the
        # deterministic checker ALSO cannot find it in the passages / tool output / question.
        # (Observed failure: the 8B judge flags sentences copied verbatim from a passage.)
        overruled = []
        if lj and lj["unsupported_claims"]:
            kept = []
            for cl in lj["unsupported_claims"]:
                if fact_in_text(cl, evidence, 0.75) or fact_in_text(cl, case["question"], 0.75):
                    overruled.append(cl)
                else:
                    kept.append(cl)
            lj["unsupported_claims"] = kept
            if not kept:
                lj["grounded"] = True
        q_nums = numbers(case["question"])
        ev_nums = numbers(evidence)
        ungrounded = sorted(n for n in numbers(answer) - ev_nums - q_nums if not re.fullmatch(r"[0-9]", n))
        cited_ok = bool(set(resp.get("cited_docs", [])) & (exp | {f"tool:{t}" for t in tool_used})) or bool(resp.get("citations") and not exp)
        llm_ungrounded = bool(lj and not lj["grounded"] and lj["unsupported_claims"])
        grounded = cited_ok and not ungrounded and not (llm_ungrounded and self.llm_mode == "full")
        passed = correct and grounded
        reasons = []
        if not correct:
            missing = [f for f, ok in zip(facts, final) if not ok]
            reasons.append(f"missing expected facts {missing}")
        if not cited_ok:
            reasons.append("did not cite the expected source")
        if ungrounded:
            reasons.append(f"numbers not found in any passage/tool output: {ungrounded}")
        if llm_ungrounded:
            reasons.append(f"judge flagged unsupported claims: {lj['unsupported_claims'][:2]}")
        if case.get("requires_tool") and case["requires_tool"] not in tool_used:
            reasons.append(f"expected tool {case['requires_tool']} was not called")
        v.update(passed=passed, correct=correct, grounded=grounded, fact_score=round(fact_score, 2), det_facts=det,
                 llm_facts=lj["verdicts"] if lj else None, llm_unsupported=lj["unsupported_claims"] if lj else [],
                 judge_disagreements=disagreements + len(overruled), judge_flags_overruled=overruled, ungrounded_numbers=ungrounded, cited_expected=cited_ok,
                 reason="; ".join(reasons) or "correct and grounded")
        # failure taxonomy (assignment categories)
        if passed:
            v["category"] = None
        elif not hit:
            v["category"] = "retrieval_miss"
        elif ungrounded or llm_ungrounded or (lj and "contradicted" in lj["verdicts"]):
            v["category"] = "hallucination"
        else:
            v["category"] = "prompt_defect"
        return v

    # ------------------------------------------------------------------ pairwise (position-debiased)
    def pairwise(self, question: str, facts: list[str], a: str, b: str) -> str:
        """Returns 'A', 'B' or 'tie'. Asked twice with swapped order; disagreement => tie."""
        def ask(x, y):
            try:
                r = llm.chat_json(llm.render("pairwise", question=question, facts="; ".join(facts), a=x, b=y),
                                  validate=llm.require_keys("winner"), model=self.model, max_tokens=150)
                return str(r.get("winner", "tie")).upper()
            except Exception:
                return "TIE"
        first, second = ask(a, b), ask(b, a)
        w1 = {"X": "A", "Y": "B"}.get(first, "tie")
        w2 = {"X": "B", "Y": "A"}.get(second, "tie")
        return w1 if w1 == w2 else "tie"

    # ------------------------------------------------------------------ calibration canaries
    def calibrate(self, cases: list[dict], n: int = 5, seed: int = 3) -> dict:
        """Plant answers whose correct verdict we KNOW, and measure the LLM judge on them."""
        rng = random.Random(seed)
        pool = [c for c in cases if c["expected_behavior"] == "answer" and c.get("key_facts")]
        rng.shuffle(pool)
        pool = pool[:n]
        results = []
        position_consistent, position_total = 0, 0
        for c in pool:
            facts = c["key_facts"]
            corrupted = [_corrupt(f) for f in facts]
            filler = ("Thank you for your question. This is an important matter and our organisation takes it very seriously. "
                      "In accordance with the applicable guidelines and after careful consideration of all relevant circumstances, ")
            canaries = {
                "gold": ("Per the documentation: " + "; ".join(facts) + ".", True),
                "terse_correct": ("; ".join(facts), True),
                "corrupted": ("Per the documentation: " + "; ".join(corrupted) + ".", False),
                "verbose_wrong": (filler * 2 + "; ".join(corrupted) + ". " + filler + "please let us know if anything else is needed.", False),
            }
            psg = "\n".join(f"[S{i+1}] {f}" for i, f in enumerate(facts))
            for kind, (ans, should_pass) in canaries.items():
                lj = self._llm_facts(c["question"], facts, psg, ans)
                det = all(fact_in_text(f, ans, 0.7) for f in facts)
                llm_pass = None
                if lj:
                    llm_pass = sum(v == "stated" for v in lj["verdicts"]) / len(facts) >= 0.6
                    if kind == "gold" and len(facts) >= 2:
                        # position probe: same facts, reversed order
                        lj_rev = self._llm_facts(c["question"], facts[::-1], psg, ans)
                        if lj_rev:
                            position_total += 1
                            position_consistent += int(lj_rev["verdicts"][::-1] == lj["verdicts"])
                results.append({"case": c["id"], "canary": kind, "expected_pass": should_pass, "llm_pass": llm_pass, "det_pass": det})
        def acc(key, kinds=None):
            rs = [r for r in results if r[key] is not None and (kinds is None or r["canary"] in kinds)]
            return round(sum(r[key] == r["expected_pass"] for r in rs) / len(rs), 2) if rs else None
        llm_acc = acc("llm_pass")
        cal = {
            "n_canaries": len(results),
            "llm_judge_accuracy": llm_acc,
            "deterministic_accuracy": acc("det_pass"),
            "llm_verbosity_trap_accuracy": acc("llm_pass", {"verbose_wrong"}),
            "llm_false_accept_rate_on_corrupted": round(1 - (acc("llm_pass", {"corrupted", "verbose_wrong"}) or 0), 2) if llm_acc is not None else None,
            "position_consistency": round(position_consistent / position_total, 2) if position_total else None,
            "judge_model": self.model,
            "agent_model": SETTINGS.model,
            "self_preference_guard": "different model family" if self.model.split(":")[0][:4] != SETTINGS.model.split(":")[0][:4] else "SAME MODEL - weaker guard",
            "details": results,
        }
        if llm_acc is None:
            self.llm_mode = "off"
        elif llm_acc < 0.75:
            self.llm_mode = "advisory"
        cal["llm_mode"] = self.llm_mode
        cal["policy"] = {"full": "LLM may credit paraphrased facts the string matcher missed; numbers always checked deterministically",
                         "advisory": "LLM judge was unreliable on canaries -> it may only veto, never grant credit",
                         "off": "LLM judge unavailable -> deterministic checks only"}[self.llm_mode]
        self.calibration = cal
        return cal


def _corrupt(fact: str) -> str:
    """Change the meaning of a fact while keeping its surface form."""
    nums = re.findall(r"\d+(?:\.\d+)?", fact)
    if nums:
        n = nums[0]
        new = str(int(float(n)) * 2 + 1) if "." not in n else str(round(float(n) * 2 + 1, 2))
        return fact.replace(n, new, 1)
    for a, b in (("not ", ""), (" must ", " must not "), (" is ", " is not "), (" are ", " are not "), (" may ", " may not "), (" can ", " cannot ")):
        if a in f" {fact} ":
            return f" {fact} ".replace(a, b, 1).strip()
    return "it is not the case that " + fact
