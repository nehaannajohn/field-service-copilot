import numpy as np
import pytest

from offline_pipeline.chunk import Chunk
from offline_pipeline.index import connect, replace_document
from online_query.retrieve import fetch_permitted, resolve_access, retrieve


def chunk(cid, text, key):
    return Chunk(cid, f"corpus/{cid}.pdf", cid, "manual", "unknown", "unknown",
                 {"page": 1, "section_path": []}, cid, text, text, "en", [], key)


def vec(i, dim=1024):
    v = np.zeros(dim, dtype=np.float32)
    v[i] = 1.0
    return v


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "index.db")
    docs = [chunk("public", "Work order guide: E-31 needs HV certification", ""),
            chunk("compressors", "E-31 is a VFD overcurrent trip on the VRS-110", "family-compressors"),
            chunk("hv_proc", "E-31 reset: measure TP1 TP2 below 50 V DC", "cert-hv|family-compressors"),
            chunk("lead", "Q2 first-time fix 74%", "role-lead")]
    for i, c in enumerate(docs):
        replace_document(conn, c.doc_path, [c], [vec(i)])
    return conn


def test_resolve_access_uses_keys_present_in_index(conn):
    assert resolve_access(conn, "u03") == {"", "family-compressors"}            # Priya: no cert-hv, no role-lead
    assert resolve_access(conn, "u02") == {"", "family-compressors", "cert-hv|family-compressors"}


def test_bm25_statistics_ignore_restricted_chunks(conn):
    _, n_docs, _ = fetch_permitted(conn, resolve_access(conn, "u03"))
    assert n_docs == 2   # public + compressors; hv_proc and lead are not counted


def test_restricted_chunk_never_returned_even_when_it_matches_best(conn):
    results = retrieve(conn, "E-31 reset TP1 TP2 50 V", "u03", query_vector=vec(2))   # vector points at hv_proc
    assert "hv_proc" not in {r.chunk_id for r in results}
    assert {r.acl_key for r in results} <= {"", "family-compressors"}


def test_permitted_user_gets_the_restricted_chunk(conn):
    results = retrieve(conn, "E-31 reset TP1 TP2 50 V", "u02", query_vector=vec(2))
    assert results[0].chunk_id == "hv_proc"


def test_unknown_user_is_rejected(conn):
    with pytest.raises(KeyError):
        resolve_access(conn, "u99")
