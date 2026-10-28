from common.config import load_config
from offline_pipeline.chunk import build_chunks, group_threads, merge_sections, split_text_pair
from offline_pipeline.reconcile import FileRecord

CORPUS = load_config()["paths"]["corpus_dir"]


def unit(text, record_id=None, parent_id=None, section_path=(), lang="en"):
    return {"unit_type": "record" if record_id else "section", "parent_id": parent_id, "lang": lang,
            "text_original": text, "text_en": text,
            "locator": {"page": None, "section_path": list(section_path), "record_id": record_id,
                        "sender": None, "date": None}}


def result(units, doc_type="unknown"):
    return {"metadata": {"doc_type": doc_type, "doc_number": "unknown", "revision": "unknown",
                         "effective_date": "unknown"},
            "transformations_applied": ["structure_inference"], "units": units}


def servio_record():
    return FileRecord(CORPUS / "data/servio_export_EU_2023-2026.csv", "h", 1, "region-eu")


def test_replies_grouped_under_root_across_parts():
    part1 = [unit("root", "m1"), unit("other", "m9")]
    part2 = [unit("reply", "m2", parent_id="m1"), unit("reply to reply", "m3", parent_id="m2")]
    groups = group_threads(part1 + part2)
    assert [[u["text_original"] for u in g] for g in groups] == [["root", "reply", "reply to reply"], ["other"]]


def test_long_text_split_with_overlap_and_aligned_original():
    paras = [f"paragraph {i} " + "word " * 900 for i in range(4)]
    pieces = split_text_pair("\n\n".join(paras), "\n\n".join(paras), limit=2000)
    assert len(pieces) > 1
    assert pieces[0][1].split("\n\n")[-1] == pieces[1][1].split("\n\n")[0]   # one paragraph of overlap
    assert all(o == e for o, e in pieces)


def test_title_and_doc_type_fall_back_to_permissions():
    [chunk] = build_chunks(servio_record(), [result([unit("werkorder: 2300121", "2300121")])])
    assert chunk.doc_title == "Servio export EU" and chunk.doc_type == "cmms"
    assert chunk.header == "Servio export EU | 2300121"
    assert chunk.acl_key == "region-eu"


def test_chunk_ids_are_stable():
    make = lambda: build_chunks(servio_record(), [result([unit("a", "1"), unit("b", "2")])])
    assert [c.chunk_id for c in make()] == [c.chunk_id for c in make()]


def test_units_with_same_locator_get_distinct_ids():
    chunks = build_chunks(servio_record(), [result([unit("first", section_path=["8.7"]),
                                                    unit("between", section_path=["8.8"]),
                                                    unit("second", section_path=["8.7"])])])
    assert len({c.chunk_id for c in chunks}) == 3


def test_empty_units_are_dropped():
    assert [u["text_original"] for u in merge_sections([unit(""), unit("text", section_path=["1"])])] == ["text"]


def test_consecutive_units_of_same_section_merge():
    merged = merge_sections([unit("step 1", section_path=["6.2"]), unit("step 2", section_path=["6.2"]),
                             unit("next", section_path=["6.3"])])
    assert [u["text_original"] for u in merged] == ["step 1\n\nstep 2", "next"]


def test_records_are_never_merged():
    merged = merge_sections([unit("row 1", "1"), unit("row 2", "2")])
    assert len(merged) == 2
