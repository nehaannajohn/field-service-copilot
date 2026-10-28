"""Retrieval runner: permitted keys -> query embedding -> filtered fetches -> BM25 and vector ranking -> fusion."""
import json
import sqlite3
from dataclasses import dataclass

import numpy as np

from common.access import permitted_keys, users
from common.config import load_config
from common.llm import embed
from online_query.retrieval_algorithms import BM25, Hybrid, VectorRanker, tokenize


@dataclass
class Retrieved:
    chunk_id: str
    doc_path: str
    doc_title: str
    doc_type: str
    revision: str
    effective_date: str
    locator: dict
    header: str
    text_original: str
    text_en: str
    acl_key: str
    cosine: float | None      # similarity to the question, used later for confidence
    bm25_rank: int | None
    vector_rank: int | None
    rrf: float


def resolve_access(conn: sqlite3.Connection, user_id: str) -> set[str]:
    """The user's permitted keys among the access keys that exist in the index."""
    if user_id not in users():
        raise KeyError(f"unknown user {user_id!r}")
    all_keys = {k for (k,) in conn.execute("SELECT DISTINCT acl_key FROM chunks")}
    return permitted_keys(user_id, all_keys)


def embed_question(question: str) -> np.ndarray:
    """Same embedding model and function as ingestion."""
    return np.asarray(embed([question])[0], dtype=np.float32)


def fetch_keyword_matches(conn, question: str, keys: set[str]) -> dict[str, str]:
    """Permitted chunks containing at least one query term (FTS5 match, filtered by access). No ranking here."""
    terms = sorted(set(tokenize(question)))
    if not terms or not keys:
        return {}
    marks = ",".join("?" * len(keys))
    rows = conn.execute(
        f"""SELECT c.chunk_id, c.header || ' ' || c.text_en || ' ' || c.text_original
            FROM chunks_fts f JOIN chunks c ON c.chunk_id = f.chunk_id
            WHERE chunks_fts MATCH ? AND c.acl_key IN ({marks})""",
        (" OR ".join(f'"{t}"' for t in terms), *sorted(keys)),
    ).fetchall()
    return dict(rows)


def fetch_permitted(conn, keys: set[str]) -> tuple[dict[str, np.ndarray], int, float]:
    """Vectors of all permitted chunks, plus their count and average token length (for BM25)."""
    if not keys:
        return {}, 0, 0.0
    marks = ",".join("?" * len(keys))
    rows = conn.execute(
        f"""SELECT chunk_id, vector, header || ' ' || text_en || ' ' || text_original
            FROM chunks WHERE acl_key IN ({marks})""", sorted(keys)).fetchall()
    vectors = {cid: np.frombuffer(blob, dtype=np.float32) for cid, blob, _ in rows}
    avg_len = sum(len(tokenize(text)) for _, _, text in rows) / len(rows) if rows else 0.0
    return vectors, len(rows), avg_len


def retrieve(conn, question: str, user_id: str, query_vector: np.ndarray | None = None) -> list[Retrieved]:
    """Top chunks for the question, from the chunks this user may see.
    query_vector can be passed in (tests); otherwise the question is embedded."""
    cfg = load_config()["retrieval"]
    keys = resolve_access(conn, user_id)
    if query_vector is None:
        query_vector = embed_question(question)

    candidates = fetch_keyword_matches(conn, question, keys)
    vectors, n_docs, avg_len = fetch_permitted(conn, keys)

    bm25 = BM25(cfg["bm25_k1"], cfg["bm25_b"]).rank(question, candidates, n_docs, avg_len)[:cfg["candidates_per_method"]]
    vector = VectorRanker().rank(query_vector, vectors)[:cfg["candidates_per_method"]]
    bm25_ids, vector_ids = [cid for cid, _ in bm25], [cid for cid, _ in vector]
    fused = Hybrid(cfg["rrf_k"]).fuse([bm25_ids, vector_ids])[:cfg["top_k"]]

    cosines = dict(vector)
    return [load_retrieved(conn, cid, rrf, cosines.get(cid), bm25_ids, vector_ids, keys) for cid, rrf in fused]


def load_retrieved(conn, chunk_id, rrf, cosine, bm25_ids, vector_ids, keys) -> Retrieved:
    row = conn.execute(
        """SELECT chunk_id, doc_path, doc_title, doc_type, revision, effective_date, locator, header,
                  text_original, text_en, acl_key FROM chunks WHERE chunk_id = ?""", (chunk_id,)).fetchone()
    if row[10] not in keys:   # defence in depth: never return a chunk outside the user's keys
        raise PermissionError(f"chunk {chunk_id} is not permitted")
    return Retrieved(*row[:6], json.loads(row[6]), *row[7:], cosine=cosine,
                     bm25_rank=bm25_ids.index(chunk_id) + 1 if chunk_id in bm25_ids else None,
                     vector_rank=vector_ids.index(chunk_id) + 1 if chunk_id in vector_ids else None,
                     rrf=rrf)
