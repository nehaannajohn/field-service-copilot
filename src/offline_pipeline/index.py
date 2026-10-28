"""SQLite index: chunk rows with embeddings, and an FTS5 table for BM25 keyword search."""
import json
import sqlite3
from pathlib import Path

import numpy as np

from common.config import load_config
from offline_pipeline.chunk import Chunk

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_path TEXT NOT NULL,
    doc_title TEXT, doc_type TEXT, revision TEXT, effective_date TEXT,
    locator TEXT NOT NULL,                 -- JSON
    header TEXT NOT NULL,
    text_original TEXT NOT NULL,
    text_en TEXT NOT NULL,
    lang TEXT,
    transformations_applied TEXT NOT NULL, -- JSON list
    acl_key TEXT NOT NULL,
    vector BLOB NOT NULL                   -- float32, embedding of header + text_en
);
CREATE INDEX IF NOT EXISTS chunks_acl ON chunks(acl_key);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_path);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED, header, text_en, text_original,
    tokenize = "unicode61 tokenchars '-'"
);
"""


STATUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_status (
    path TEXT PRIMARY KEY,                 -- relative to data/
    acl_key TEXT NOT NULL,
    status TEXT NOT NULL,                  -- indexed | not_indexed | error | duplicate
    reason TEXT,
    flags TEXT NOT NULL,                   -- JSON list
    parts INTEGER, chunks INTEGER,
    cached INTEGER,                        -- 1 if the parse came from cache in its last run
    transformations_applied TEXT,          -- JSON list
    updated_at TEXT NOT NULL
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or load_config()["paths"]["index_db"]
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executescript(STATUS_SCHEMA)
    return conn


def embedding_text(chunk: Chunk) -> str:
    return f"{chunk.header}\n{chunk.text_en}"


def replace_document(conn: sqlite3.Connection, doc_path: str, chunks: list[Chunk],
                     vectors: list[list[float]]) -> None:
    """Delete a document's old chunks and write its new ones, in one transaction."""
    with conn:
        old_ids = [r[0] for r in conn.execute("SELECT chunk_id FROM chunks WHERE doc_path = ?", (doc_path,))]
        conn.executemany("DELETE FROM chunks_fts WHERE chunk_id = ?", [(i,) for i in old_ids])
        conn.execute("DELETE FROM chunks WHERE doc_path = ?", (doc_path,))
        for chunk, vector in zip(chunks, vectors, strict=True):
            conn.execute(
                "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (chunk.chunk_id, chunk.doc_path, chunk.doc_title, chunk.doc_type, chunk.revision,
                 chunk.effective_date, json.dumps(chunk.locator), chunk.header, chunk.text_original,
                 chunk.text_en, chunk.lang, json.dumps(chunk.transformations_applied), chunk.acl_key,
                 np.asarray(vector, dtype=np.float32).tobytes()),
            )
            conn.execute("INSERT INTO chunks_fts VALUES (?,?,?,?)",
                         (chunk.chunk_id, chunk.header, chunk.text_en, chunk.text_original))


def remove_documents(conn: sqlite3.Connection, keep_paths: set[str]) -> list[str]:
    """Delete chunks of documents no longer in the corpus. Returns the removed doc paths."""
    indexed = {r[0] for r in conn.execute("SELECT DISTINCT doc_path FROM chunks")}
    removed = sorted(indexed - keep_paths)
    for doc_path in removed:
        replace_document(conn, doc_path, [], [])
    return removed


def save_status(conn: sqlite3.Connection, entry: dict) -> None:
    """Insert or replace one file's latest status."""
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_status VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            (entry["path"], entry["acl_key"], entry["status"], entry.get("reason"),
             json.dumps(entry.get("flags", [])), entry.get("parts"), entry.get("chunks"),
             int(entry["cached"]) if "cached" in entry else None,
             json.dumps(entry.get("transformations_applied", []))),
        )


def remove_statuses(conn: sqlite3.Connection, keep_paths: set[str]) -> None:
    """Drop status rows for files no longer in the corpus (full runs only)."""
    with conn:
        for (path,) in conn.execute("SELECT path FROM ingest_status").fetchall():
            if path not in keep_paths:
                conn.execute("DELETE FROM ingest_status WHERE path = ?", (path,))


def all_statuses(conn: sqlite3.Connection) -> list[dict]:
    """Every saved status, ordered by path. Empty fields are left out."""
    columns = ["path", "acl_key", "status", "reason", "flags", "parts", "chunks", "cached",
               "transformations_applied", "updated_at"]
    rows = conn.execute(f"SELECT {', '.join(columns)} FROM ingest_status ORDER BY path").fetchall()
    out = []
    for row in rows:
        entry = dict(zip(columns, row))
        entry["flags"] = json.loads(entry["flags"])
        entry["transformations_applied"] = json.loads(entry["transformations_applied"] or "[]")
        out.append({k: v for k, v in entry.items() if v is not None})
    return out
