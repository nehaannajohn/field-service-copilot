from online_query.pipeline import render_answer, submit_work_order

RESULT = {
    "status": "answered", "message": None, "work_order": None,
    "summary": [{"sentence": "Sources disagree: 38 N-m vs 45 N-m.", "sources": ["S1", "S2"]}],
    "evidence": [
        {"sentence": "Sources disagree: 38 N-m vs 45 N-m.", "source": "S1", "status": "Supported",
         "title": "Halden SB-2025-009", "location": "p.1", "revision": "0", "date": "2025-01-01"},
        {"sentence": "Sources disagree: 38 N-m vs 45 N-m.", "source": "S2", "status": "Contradicted",
         "title": "Halden HCP-350 IOM", "location": "p.9 · 8.7", "revision": "Rev D", "date": "unknown"}],
}


def test_summary_markers_show_status():
    assert "[S1 ✓, S2 ✗]" in render_answer(RESULT)


def test_abstain_shows_only_the_message():
    assert render_answer({"status": "no_permitted_source", "message": "No document you have access to covers this."}) \
        == "No document you have access to covers this."


def test_approved_work_order_is_written_to_outbox(tmp_path, monkeypatch):
    from common import config
    cfg = config.load_config()
    monkeypatch.setitem(cfg["paths"], "outbox_dir", tmp_path / "outbox")
    message = submit_work_order({"requested_by": "u03", "fault_code": "E-31"}, approved=True)
    files = list((tmp_path / "outbox").glob("WO-*-u03.json"))
    assert len(files) == 1 and "submitted for supervisor approval" in message


def test_rejected_work_order_writes_nothing(tmp_path, monkeypatch):
    from common import config
    cfg = config.load_config()
    monkeypatch.setitem(cfg["paths"], "outbox_dir", tmp_path / "outbox")
    assert submit_work_order({"requested_by": "u03"}, approved=False) == "Work order discarded."
    assert not (tmp_path / "outbox").exists()
