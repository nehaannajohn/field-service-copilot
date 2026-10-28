from offline_pipeline.reconcile import reconcile


def test_every_corpus_file_gets_a_record():
    assert len(reconcile()) == 42


def test_only_unofficial_page_has_deny_key():
    flagged = [r.path.name for r in reconcile() if "no_permission_entry" in r.flags]
    assert flagged == ["VRS-110-VFD-quick-reset-unofficial.html"]


def test_no_file_lacks_an_eligible_user_today():
    assert not [r for r in reconcile() if "no_current_eligible_user" in r.flags]
