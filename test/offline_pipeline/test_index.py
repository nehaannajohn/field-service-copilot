import numpy as np

from offline_pipeline.chunk import Chunk
from offline_pipeline.index import (all_statuses, connect, remove_documents, remove_statuses,
                                    replace_document, save_status)


def chunk(chunk_id, doc="corpus/a.pdf", text="Casing bolt torque 38 N-m for E-31", key="family-pumps"):
    return Chunk(chunk_id, doc, "Doc A", "manual", "Rev D", "unknown", {"page": 1, "section_path": []},
                 "Doc A | Rev D", text, text, "en", [], key)


def test_write_and_read_back(tmp_path):
    conn = connect(tmp_path / "index.db")
    replace_document(conn, "corpus/a.pdf", [chunk("c1")], [[0.5] * 1024])
    row = conn.execute("SELECT acl_key, vector FROM chunks WHERE chunk_id = 'c1'").fetchone()
    assert row[0] == "family-pumps"
    assert np.frombuffer(row[1], dtype=np.float32).shape == (1024,)


def test_reingest_replaces_old_chunks(tmp_path):
    conn = connect(tmp_path / "index.db")
    replace_document(conn, "corpus/a.pdf", [chunk("c1"), chunk("c2")], [[0.0] * 1024] * 2)
    replace_document(conn, "corpus/a.pdf", [chunk("c3")], [[0.0] * 1024])
    assert [r[0] for r in conn.execute("SELECT chunk_id FROM chunks")] == ["c3"]
    assert [r[0] for r in conn.execute("SELECT chunk_id FROM chunks_fts")] == ["c3"]


def test_hyphenated_code_is_one_keyword(tmp_path):
    conn = connect(tmp_path / "index.db")
    replace_document(conn, "corpus/a.pdf", [chunk("c1")], [[0.0] * 1024])
    hits = conn.execute("""SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH '"E-31"'""").fetchall()
    assert hits == [("c1",)]


def test_documents_no_longer_in_corpus_are_removed(tmp_path):
    conn = connect(tmp_path / "index.db")
    replace_document(conn, "corpus/a.pdf", [chunk("c1")], [[0.0] * 1024])
    replace_document(conn, "corpus/b.pdf", [chunk("c2", doc="corpus/b.pdf")], [[0.0] * 1024])
    assert remove_documents(conn, {"corpus/a.pdf"}) == ["corpus/b.pdf"]
    assert [r[0] for r in conn.execute("SELECT chunk_id FROM chunks")] == ["c1"]


def test_status_is_updated_per_file_not_replaced(tmp_path):
    conn = connect(tmp_path / "index.db")
    save_status(conn, {"path": "corpus/a.pdf", "acl_key": "k", "status": "not_indexed", "reason": "x"})
    save_status(conn, {"path": "corpus/b.pdf", "acl_key": "k", "status": "indexed", "chunks": 3})
    save_status(conn, {"path": "corpus/a.pdf", "acl_key": "k", "status": "indexed", "chunks": 5})   # a later sample run
    statuses = {s["path"]: s for s in all_statuses(conn)}
    assert set(statuses) == {"corpus/a.pdf", "corpus/b.pdf"}
    assert statuses["corpus/a.pdf"]["status"] == "indexed" and "reason" not in statuses["corpus/a.pdf"]


def test_statuses_of_deleted_files_are_removed(tmp_path):
    conn = connect(tmp_path / "index.db")
    save_status(conn, {"path": "corpus/a.pdf", "acl_key": "k", "status": "indexed"})
    save_status(conn, {"path": "corpus/gone.pdf", "acl_key": "k", "status": "indexed"})
    remove_statuses(conn, {"corpus/a.pdf"})
    assert [s["path"] for s in all_statuses(conn)] == ["corpus/a.pdf"]

