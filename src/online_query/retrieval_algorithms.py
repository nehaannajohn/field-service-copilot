"""Ranking algorithms for retrieval: BM25 over permitted chunks, cosine similarity, reciprocal rank fusion."""
import math
import re
from collections import Counter

import numpy as np

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9]|[A-Za-z0-9]")


def tokenize(text: str) -> list[str]:
    """Lower-cased words and codes; codes like E-31 or TAC-C-0143 stay whole."""
    return [t.lower() for t in TOKEN.findall(text)]


class BM25:
    def __init__(self, k1: float, b: float):
        # k1: term-frequency saturation. Each extra occurrence of a term adds less to the score;
        #     higher k1 lets repeated terms keep counting for longer (0 = presence only). Typical 1.2-2.0.
        # b:  length normalisation. 1 = fully penalise chunks longer than average, 0 = ignore length.
        #     Typical 0.75.
        self.k1, self.b = k1, b

    def rank(self, query: str, candidates: dict[str, str], n_docs: int, avg_len: float) -> list[tuple[str, float]]:
        """candidates: chunk_id -> text of every permitted chunk that matches at least one query term.
        n_docs, avg_len: chunk count and average token length over all permitted chunks.
        Returns (chunk_id, score), best first."""
        terms = set(tokenize(query))
        docs = {cid: Counter(tokenize(text)) for cid, text in candidates.items()}
        # Every permitted chunk containing a term is a candidate, so document frequency is exact.
        df = {t: sum(1 for tf in docs.values() if t in tf) for t in terms}
        scores = {}
        for cid, tf in docs.items():
            length = sum(tf.values())
            score = 0.0
            for t in terms:
                if tf[t]:
                    idf = math.log(1 + (n_docs - df[t] + 0.5) / (df[t] + 0.5))
                    score += idf * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * length / avg_len))
            scores[cid] = score
        return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


class VectorRanker:
    def rank(self, query_vector: np.ndarray, vectors: dict[str, np.ndarray]) -> list[tuple[str, float]]:
        """vectors: chunk_id -> embedding of every permitted chunk. Returns (chunk_id, cosine), best first."""
        if not vectors:
            return []
        ids = list(vectors)
        matrix = np.stack([vectors[i] for i in ids])
        cosine = matrix @ query_vector / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vector) + 1e-12)
        return sorted(zip(ids, cosine.tolist()), key=lambda kv: kv[1], reverse=True)


class Hybrid:
    def __init__(self, k: int):
        # k: damping constant in 1 / (k + rank). Larger k flattens the gap between top and lower ranks,
        #    so agreement between the two rankings matters more than being first in one. 60 is the standard value.
        self.k = k

    def fuse(self, rankings: list[list[str]]) -> list[tuple[str, float]]:
        """rankings: lists of chunk ids, best first. Score = sum of 1 / (k + rank). Returns best first."""
        scores: dict[str, float] = {}
        for ranking in rankings:
            for rank, chunk_id in enumerate(ranking, 1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (self.k + rank)
        return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
