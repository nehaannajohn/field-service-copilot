import math

import numpy as np

from online_query.retrieval_algorithms import BM25, Hybrid, VectorRanker, tokenize


def test_tokenize_keeps_codes_whole():
    assert tokenize("TAC-C-0143 tripped on E-31. Reset?") == ["tac-c-0143", "tripped", "on", "e-31", "reset"]


def test_bm25_matches_hand_computed_score():
    # one term, one candidate of length 2, collection of 10 chunks with average length 2
    [(cid, score)] = BM25(k1=1.2, b=0.75).rank("e-31", {"c1": "E-31 trip"}, n_docs=10, avg_len=2.0)
    idf = math.log(1 + (10 - 1 + 0.5) / (1 + 0.5))
    assert cid == "c1" and math.isclose(score, idf * 1 * 2.2 / (1 + 1.2))


def test_bm25_rare_code_outranks_common_word():
    # 'e-31' is in 1 chunk; 'reset' is in 501, so it carries little weight even when repeated
    candidates = {"code": "E-31 overcurrent", "common": "reset the unit reset"}
    candidates |= {f"r{i}": "reset" for i in range(500)}
    ranked = BM25(1.2, 0.75).rank("E-31 reset", candidates, n_docs=1000, avg_len=3.0)
    assert ranked[0][0] == "code"


def test_vector_ranker_orders_by_cosine():
    q = np.array([1.0, 0.0], dtype=np.float32)
    ranked = VectorRanker().rank(q, {"near": np.array([0.9, 0.1], dtype=np.float32),
                                     "far": np.array([0.0, 1.0], dtype=np.float32)})
    assert [cid for cid, _ in ranked] == ["near", "far"]


def test_hybrid_rewards_chunks_found_by_both_methods():
    fused = Hybrid(k=60).fuse([["a", "b"], ["b", "c"]])
    assert fused[0][0] == "b"
