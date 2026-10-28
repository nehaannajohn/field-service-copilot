"""Run ingestion over the corpus: reconcile, dedupe, parse (cached, parallel), chunk, embed (cached), index."""
import hashlib
import json
import sqlite3
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from common.config import load_config
from common.llm import embed
from offline_pipeline.checks import IncompleteParse, parse_checked
from offline_pipeline.chunk import build_chunks
from offline_pipeline.dedupe import dedupe
from offline_pipeline.index import (all_statuses, connect, embedding_text, remove_documents, remove_statuses,
                                    replace_document, save_status)
from offline_pipeline.inputs import ModelInput, Unreadable, build_inputs
from offline_pipeline.parse import INSTRUCTIONS, SCHEMA
from offline_pipeline.reconcile import FileRecord, reconcile


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fingerprint(inputs: list[ModelInput]) -> dict:
    """What a cached parse depends on: the ingest model, the prompt, and the exact parts sent."""
    return {
        "ingest_model": load_config()["models"]["ingest"],
        "prompt": sha(INSTRUCTIONS + json.dumps(SCHEMA, sort_keys=True)),
        "inputs": sha(json.dumps([i.content for i in inputs], sort_keys=True)),
    }


def parse_file(record: FileRecord, pool: ThreadPoolExecutor) -> tuple[list[dict], bool]:
    """Checked parse results for every part, cached under the file's content hash.
    The cached entry is reused only if its fingerprint matches; otherwise it is re-parsed and replaced."""
    cache_file = load_config()["paths"]["cache_dir"] / "parse" / f"{record.content_hash}.json"
    inputs = build_inputs(record.path)
    current = fingerprint(inputs)
    if cache_file.exists():
        entry = json.loads(cache_file.read_text())
        if entry["fingerprint"] == current:
            return entry["results"], True
    results = list(pool.map(lambda part: parse_checked(record.path, part), inputs))
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"fingerprint": current, "results": results}, ensure_ascii=False))
    return results, False


class EmbeddingCache:
    """Embeddings keyed by hash(embedding model + text), so unchanged chunks are never re-embedded."""

    def __init__(self):
        path = load_config()["paths"]["cache_dir"] / "embeddings.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vector BLOB)")
        self.model = load_config()["models"]["embedding"]

    def vectors(self, texts: list[str]) -> list[list[float]]:
        keys = [sha(f"{self.model}|{t}") for t in texts]
        found = {k: v for k, v in self.conn.execute(
            f"SELECT key, vector FROM emb WHERE key IN ({','.join('?' * len(keys))})", keys)}
        missing = [i for i, k in enumerate(keys) if k not in found]
        if missing:
            new = embed([texts[i] for i in missing])
            with self.conn:
                for i, vector in zip(missing, new):
                    blob = np.asarray(vector, dtype=np.float32).tobytes()
                    self.conn.execute("INSERT OR REPLACE INTO emb VALUES (?, ?)", (keys[i], blob))
                    found[keys[i]] = blob
        return [np.frombuffer(found[k], dtype=np.float32).tolist() for k in keys]


def restrict_to_sample(records, kept, duplicates, only: set[str], data_dir):
    """After deduping the whole corpus, keep only the sampled files (paths relative to data/)."""
    rel = lambda r: r.path.relative_to(data_dir).as_posix()
    return ([r for r in records if rel(r) in only], [r for r in kept if rel(r) in only],
            [d for d in duplicates if rel(d.record) in only])


def ingest(only: set[str] | None = None) -> dict:
    """only: paths relative to data/ to ingest as a sample; None ingests the whole corpus."""
    cfg = load_config()
    start = time.time()
    records = reconcile()
    kept, duplicates = dedupe(records)          # always across the whole corpus
    if only is not None:
        records, kept, duplicates = restrict_to_sample(records, kept, duplicates, only, cfg["paths"]["data_dir"])
    conn, embeddings = connect(), EmbeddingCache()
    data_dir = cfg["paths"]["data_dir"]
    rel = lambda r: r.path.relative_to(data_dir).as_posix()

    # 1. Duplicates: save their status straight away.
    for d in duplicates:
        save_status(conn, {"path": rel(d.record), "acl_key": d.record.acl_key, "status": "duplicate",
                           "reason": f"same content and access as {rel(d.duplicate_of)}", "flags": d.record.flags})

    # 2. Each kept record: parse (cache or model) -> chunk -> embed -> index -> save its status.
    indexed_paths = set()
    with ThreadPoolExecutor(max_workers=cfg["ingest"]["max_workers"]) as pool:
        for record in kept:
            entry = {"path": rel(record), "acl_key": record.acl_key, "flags": record.flags}
            try:
                results, cached = parse_file(record, pool)
                chunks = build_chunks(record, results)
                vectors = embeddings.vectors([embedding_text(c) for c in chunks])
                replace_document(conn, rel(record), chunks, vectors)
                indexed_paths.add(rel(record))
                entry |= {"status": "indexed", "parts": len(results), "chunks": len(chunks), "cached": cached,
                          "transformations_applied": chunks[0].transformations_applied if chunks else []}
            except (Unreadable, IncompleteParse) as e:
                entry |= {"status": "not_indexed", "reason": str(e)}
            except Exception as e:   # API or parsing errors: report the file, keep going
                entry |= {"status": "error", "reason": f"{type(e).__name__}: {e}"}
            save_status(conn, entry)
            print(f"{entry['status']:12s} {entry['path']}", flush=True)

    # 3. Full run only: drop files that are no longer in the corpus, from the index and from the statuses.
    removed = []
    if only is None:
        removed = remove_documents(conn, indexed_paths)
        remove_statuses(conn, {rel(r) for r in records})

    # 4. Report: read back every saved status (this run's and earlier runs') and write the JSON file.
    files = all_statuses(conn)
    summary = {
        "corpus_files": len(files),
        "by_status": dict(Counter(f["status"] for f in files)),
        "indexed_chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "last_run": {"files_processed": len(records), "sample": only is not None,
                     "removed_from_index": removed, "seconds": round(time.time() - start, 1)},
    }
    out = {"summary": summary, "files": files}
    cfg["paths"]["ingest_report"].write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    import sys
    sample = set(sys.argv[1:]) or None   # e.g. python -m offline_pipeline.ingest corpus/manuals/x.pdf
    print(json.dumps(ingest(sample)["summary"], indent=2))
