"""BM25 / dense / hybrid (RRF) retrieval. Dense is optional: if the endpoint cannot embed,
hybrid silently degrades to BM25 and the run log says so."""
from __future__ import annotations

import math
import re
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from . import llm
from .docs import Chunk

_STOP = set(
    "a an the and or of to in on for with is are was were be been by at as it its this that these those from "
    "what which who whom how when where why do does did can could should would will shall may might must i you "
    "we they he she my our your their me us them if than then there here about into over under any all some "
    "no not per vs via".split()
)


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*", text.lower())
    out = []
    for t in toks:
        if t in _STOP:
            continue
        # tiny stemmer: good enough for BM25 recall on policy text
        for suf in ("ing", "ies", "es", "s", "ed"):
            if len(t) > 4 and t.endswith(suf) and not t[-len(suf) - 1].isdigit():
                t = t[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        out.append(t)
    return out


class Index:
    def __init__(self, chunks: list[Chunk], use_dense: bool = True):
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c.text) or ["_"] for c in chunks]) if chunks else None
        self.dense: Optional[np.ndarray] = None
        self.dense_available = False
        if use_dense and chunks:
            vecs = llm.embed([c.text for c in chunks])
            if vecs:
                m = np.array(vecs, dtype=np.float32)
                m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
                self.dense = m
                self.dense_available = True

    # ranking helpers return [(idx, score)] best first
    def _bm25_rank(self, q: str) -> list[tuple[int, float]]:
        scores = self.bm25.get_scores(tokenize(q) or ["_"])
        order = np.argsort(-scores)
        return [(int(i), float(scores[i])) for i in order]

    def _dense_rank(self, q: str) -> list[tuple[int, float]]:
        v = llm.embed([q])
        if not v or self.dense is None:
            return []
        qv = np.array(v[0], dtype=np.float32)
        qv /= np.linalg.norm(qv) + 1e-9
        sims = self.dense @ qv
        order = np.argsort(-sims)
        return [(int(i), float(sims[i])) for i in order]

    def rank(self, query: str, mode: str = "hybrid", extra_queries: Optional[list[str]] = None) -> list[tuple[Chunk, float]]:
        """Full ranking. Multiple queries (query rewriting) are fused with RRF."""
        if not self.chunks:
            return []
        queries = [query] + list(extra_queries or [])
        rankings: list[list[tuple[int, float]]] = []
        for q in queries:
            if mode in ("bm25", "hybrid") or not self.dense_available:
                rankings.append(self._bm25_rank(q))
            if mode in ("dense", "hybrid") and self.dense_available:
                rankings.append(self._dense_rank(q))
        if len(rankings) == 1:
            return [(self.chunks[i], s) for i, s in rankings[0]]
        fused: dict[int, float] = {}
        for r in rankings:
            for pos, (i, _) in enumerate(r):
                fused[i] = fused.get(i, 0.0) + 1.0 / (60 + pos + 1)
        order = sorted(fused.items(), key=lambda x: -x[1])
        return [(self.chunks[i], s) for i, s in order]

    def search(self, query: str, top_k: int = 5, mode: str = "hybrid", extra_queries: Optional[list[str]] = None) -> list[tuple[Chunk, float]]:
        return self.rank(query, mode, extra_queries)[:top_k]

    def doc_rank(self, query: str, doc: str, mode: str = "hybrid", extra_queries=None) -> int:
        """1-based rank of the first chunk from `doc` (math.inf if absent). Used by the critic."""
        for pos, (c, _) in enumerate(self.rank(query, mode, extra_queries)):
            if c.doc == doc:
                return pos + 1
        return math.inf
