from online_query.compose import chunk_status, evidence_table, location, number_sources
from online_query.retrieve import Retrieved


def chunk(cid, locator):
    return Retrieved(cid, "corpus/x.pdf", f"Doc {cid}", "manual", "Rev D", "2026-01-12", locator, cid,
                     "text", "text", "", None, None, None, 0.0)


SB = chunk("sb", {"page": 1, "section_path": ["1 Summary"], "record_id": None, "sender": None, "date": None})
IOM = chunk("iom", {"page": 9, "section_path": ["8.7"], "record_id": None, "sender": None, "date": None})
CLAIMS = [{"id": "c1", "text": "38 N-m from HCP350-240001"}, {"id": "c2", "text": "dropped claim"}]
VERIFICATION = {
    "results": {"c1": {"kept": True, "citations": ["sb"], "contradicting": ["iom"]},
                "c2": {"kept": False, "citations": ["iom"], "contradicting": []}},
    "cells": [{"claim_id": "c1", "chunk_id": "sb", "verdict": "supports", "evidence": "torque is 38 N-m"},
              {"claim_id": "c1", "chunk_id": "iom", "verdict": "contradicts", "evidence": "torque 45 N-m"}],
}


def test_sources_numbered_by_first_use_of_kept_claims_only():
    assert number_sources(CLAIMS, VERIFICATION["results"]) == {"sb": "S1", "iom": "S2"}


def test_chunk_status_from_kept_claims():
    assert chunk_status("sb", VERIFICATION) == ("Supported", "torque is 38 N-m")
    assert chunk_status("iom", VERIFICATION) == ("Contradicted", "torque 45 N-m")


def test_evidence_table_one_row_per_sentence_and_source():
    summary = [{"sentence": "Sources disagree: 38 N-m vs 45 N-m.", "sources": ["S1", "S2"]}]
    rows = evidence_table(summary, {"sb": "S1", "iom": "S2"}, [SB, IOM], VERIFICATION)
    assert [(r["source"], r["status"], r["location"]) for r in rows] == [
        ("S1", "Supported", "p.1 · 1 Summary"), ("S2", "Contradicted", "p.9 · 8.7")]
    assert rows[0]["title"] == "Doc sb" and rows[0]["date"] == "2026-01-12"


def test_invented_source_id_is_skipped():
    rows = evidence_table([{"sentence": "x", "sources": ["S1", "S9"]}], {"sb": "S1"}, [SB], VERIFICATION)
    assert [r["source"] for r in rows] == ["S1"]


def test_location_for_records_and_messages():
    record = chunk("r", {"page": None, "section_path": [], "record_id": "WO 232436", "sender": None, "date": "2026-09-22"})
    message = chunk("m", {"page": None, "section_path": [], "record_id": "m1", "sender": "Kenji", "date": "2026-07-02"})
    assert location(record) == "WO 232436 · 2026-09-22"
    assert location(message) == "m1 · Kenji, 2026-07-02"
