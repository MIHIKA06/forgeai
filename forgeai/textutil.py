"""Deterministic text checks. These are the factory's lie detectors: whenever an LLM claims
'this quote is in the document' or 'the answer states fact X', we verify it here."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?%?")
_WORDNUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
            "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30",
            "half": "0.5", "fourteen": "14", "sixty": "60", "ninety": "90", "forty": "40", "fifty": "50", "hundred": "100"}
_STOP = set("a an the and or of to in on for with is are was be by at as it its this that from per any all".split())


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"(\d),(\d{3})", r"\1\2", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.%$/\- ]+", " ", s)).strip()


def numbers(s: str) -> set[str]:
    out = set()
    for m in _NUM.findall(s.replace(",", "")):
        m = m.rstrip("%").lstrip("+")
        try:
            f = float(m)
            out.add(str(int(f)) if f == int(f) else str(f))
        except ValueError:
            pass
    for w in re.findall(r"[a-z]+", s.lower()):
        if w in _WORDNUM:
            out.add(_WORDNUM[w])
    return out


def content_words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", norm(s)) if w not in _STOP and len(w) > 1]


def _stem(w: str) -> str:
    w = re.sub(r"is(e|ed|es|ing|ation)$", r"iz\1", w)  # British/American: regularised == regularized
    w = re.sub(r"our$", "or", w) if len(w) > 5 else w  # colour == color
    for suf in ("ing", "ies", "es", "s", "ed", "ly"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def fact_in_text(fact: str, text: str, threshold: float = 0.7) -> bool:
    """True if `fact` is (approximately) stated in `text`.
    - every number in the fact must appear in the text (hard requirement)
    - >= threshold of the fact's content words (stemmed) must appear in the text."""
    fn = numbers(fact)
    if fn and not fn <= numbers(text):
        return False
    fw = {_stem(w) for w in content_words(fact)}
    if not fw:
        return bool(fn)
    tw = {_stem(w) for w in content_words(text)}
    return len(fw & tw) / len(fw) >= threshold


def quote_in_text(quote: str, text: str, threshold: float = 0.85) -> bool:
    """Is `quote` (claimed verbatim) really in `text`? Tolerates whitespace/punctuation/PDF noise."""
    q, t = norm(quote), norm(text)
    if not q:
        return False
    if q in t:
        return True
    # sliding window fuzzy match over word windows
    qw, tw = q.split(), t.split()
    n = len(qw)
    if n == 0 or len(tw) == 0:
        return False
    best = 0.0
    for i in range(0, max(1, len(tw) - n + 1)):
        window = " ".join(tw[i : i + n])
        r = SequenceMatcher(None, q, window).ratio()
        if r > best:
            best = r
            if best >= threshold:
                return True
    return best >= threshold


def similarity(a: str, b: str) -> float:
    wa, wb = set(content_words(a)), set(content_words(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


REFUSAL_PATTERNS = re.compile(
    r"(i('| a)m (sorry|unable|not able)|i can(no|')t (help|answer|assist|provide)|outside (of )?(my|the) scope|"
    r"not (covered|included|mentioned|specified|available) in|(do|does) not (contain|cover|include|mention|specify|provide)|no information (about|on|regarding)|"
    r"unable to (answer|help|provide)|please (contact|reach out to|consult)|beyond (my|the) scope|i don't have (that|this|enough) information)",
    re.I,
)


def looks_like_refusal(answer: str) -> bool:
    return bool(REFUSAL_PATTERNS.search(answer or ""))
