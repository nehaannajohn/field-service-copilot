from pathlib import Path

from offline_pipeline.dedupe import dedupe
from offline_pipeline.ingest import fingerprint, restrict_to_sample
from offline_pipeline.inputs import ModelInput
from offline_pipeline.reconcile import FileRecord


def part(text):
    return ModelInput(1, 1, {"type": "input_text", "text": text})


def test_fingerprint_same_input_same_fingerprint():
    assert fingerprint([part("abc")]) == fingerprint([part("abc")])


def test_fingerprint_changes_when_the_sent_input_changes():
    assert fingerprint([part("abc")]) != fingerprint([part("abd")])


def test_sampled_duplicate_of_unsampled_file_is_caught():
    data = Path("/data")
    old = FileRecord(data / "corpus/a_manual.pdf", "same", 1, "k")     # already in the corpus
    new = FileRecord(data / "corpus/b_manual_copy.pdf", "same", 1, "k")  # added and ingested as a sample
    records = [old, new]
    kept, duplicates = dedupe(records)
    records, kept, duplicates = restrict_to_sample(records, kept, duplicates, {"corpus/b_manual_copy.pdf"}, data)
    assert kept == [] and [d.record for d in duplicates] == [new]
