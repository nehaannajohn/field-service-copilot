from pathlib import Path

from offline_pipeline.dedupe import dedupe
from offline_pipeline.reconcile import FileRecord, reconcile


def record(name, content_hash, key):
    return FileRecord(Path(name), content_hash, 1, key)


def test_same_content_same_key_keeps_one():
    kept, dropped = dedupe([record("a.pdf", "h1", "k"), record("b.pdf", "h1", "k")])
    assert [r.path.name for r in kept] == ["a.pdf"]
    assert dropped[0].record.path.name == "b.pdf" and dropped[0].duplicate_of.path.name == "a.pdf"


def test_same_content_different_key_keeps_both():
    kept, dropped = dedupe([record("a.pdf", "h1", "k1"), record("b.pdf", "h1", "k2")])
    assert len(kept) == 2 and not dropped


def test_corpus_drops_exactly_the_nk600_duplicate():
    kept, dropped = dedupe(reconcile())
    assert len(kept) == 41
    assert {dropped[0].record.path.name, dropped[0].duplicate_of.path.name} == {
        "NK600_manual_final_v2.pdf", "Nordkyl_NK-600_Service_Manual_RevC.pdf"}
