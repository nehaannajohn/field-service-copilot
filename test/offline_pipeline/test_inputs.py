import csv
import io
import json

import pytest

from common.config import load_config
from offline_pipeline.inputs import Unreadable, build_inputs

CORPUS = load_config()["paths"]["corpus_dir"]


def test_zero_byte_file_is_unreadable():
    with pytest.raises(Unreadable):
        build_inputs(CORPUS / "sharepoint/Inspection_Checklist_Q3_FINAL.docx")


def test_pdf_is_one_file_part():
    [only] = build_inputs(CORPUS / "bulletins/Halden_SB-2025-018_Seal_Kit_Supersession.pdf")
    assert only.content["type"] == "input_file"


def test_docx_keeps_headings_and_tables():
    [only] = build_inputs(CORPUS / "sharepoint/SOP-020_Chiller_Leak_Test_and_Recharge.docx")
    assert "SOP-020" in only.content["text"] and " | " in only.content["text"]


def rows(text):
    dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|")
    return list(csv.reader(io.StringIO(text), dialect))


def test_csv_parts_repeat_header_and_lose_no_rows():
    path = CORPUS / "data/maintpro_history_NA_2023-2026.csv"
    parts = build_inputs(path)
    source = rows(path.read_text())
    assert len(parts) > 1
    assert all(rows(p.content["text"])[0] == source[0] for p in parts)
    assert sum(len(rows(p.content["text"])) - 1 for p in parts) == len(source) - 1


def test_record_parts_respect_the_record_cap():
    cap = load_config()["ingest"]["max_records_per_part"]
    servio = build_inputs(CORPUS / "data/servio_export_EU_2023-2026.csv")
    assert all(len(rows(p.content["text"])) - 1 <= cap for p in servio)
    sf = build_inputs(CORPUS / "data/salesforce_cases_NA_2025-2026.json")
    assert all(len(json.loads(p.content["text"])) <= cap for p in sf)


def test_json_parts_lose_no_records():
    parts = build_inputs(CORPUS / "data/salesforce_cases_NA_2025-2026.json")
    assert sum(len(json.loads(p.content["text"])) for p in parts) == 38


def test_html_becomes_visible_text_with_headings():
    [only] = build_inputs(CORPUS / "confluence/Compressor-Troubleshooting-Playbook.html")
    text = only.content["text"]
    assert "E-31" in text and "\n#" in text
    assert "<div" not in text and "<script" not in text


def test_eml_has_headers_and_plain_body_once():
    [only] = build_inputs(CORPUS / "email/RE_BX-12_tracking_after_belt_change.eml")
    text = only.content["text"]
    assert text.startswith("From: ") and "Subject: RE: BX-12 tracking after belt change" in text
    assert "77-0419" in text and "<html" not in text.lower()
    assert text.count("Return idlers from production lot 23-11") == 1   # body not duplicated from the HTML part
