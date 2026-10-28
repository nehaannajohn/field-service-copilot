from common.access import (PUBLIC_KEY, acl_key, deny_key, doc_acl_key, eligible_users,
                           permissions, permitted_keys, users, validate_groups)
from common.config import load_config

ALL_KEYS = {acl_key(groups) for groups in permissions().values()} | {deny_key()}
CORPUS = load_config()["paths"]["corpus_dir"]


def test_permitted_keys_match_hand_checked_list():
    # u03 Priya: region-na, family-compressors
    assert permitted_keys("u03", ALL_KEYS) == {
        PUBLIC_KEY, "region-na", "family-compressors", "family-compressors|region-na"}
    # u05 Sofie: region-eu, family-chillers, cert-refrigerant
    assert permitted_keys("u05", ALL_KEYS) == {
        PUBLIC_KEY, "region-eu", "family-chillers", "family-chillers|region-eu",
        "cert-refrigerant|family-chillers"}


def test_deny_key_never_permitted():
    for user_id in users():
        assert deny_key() not in permitted_keys(user_id, ALL_KEYS)
    assert eligible_users(deny_key()) == []


def test_public_key_visible_to_everyone():
    assert eligible_users(PUBLIC_KEY) == list(users())


def test_missing_permissions_entry_gets_deny_key():
    assert doc_acl_key(CORPUS / "confluence/VRS-110-VFD-quick-reset-unofficial.html") == deny_key()
    assert doc_acl_key(CORPUS / "sharepoint/HV-PROC-07_VRS-110_VFD_Fault_Reset.docx") == "cert-hv|family-compressors"


def test_all_groups_required_not_any():
    # u02 Daniel has cert-hv + family-compressors; u03 Priya has only family-compressors
    key = "cert-hv|family-compressors"
    assert "u02" in eligible_users(key)
    assert "u03" not in eligible_users(key)


def test_corpus_groups_do_not_use_reserved_name():
    validate_groups()  # raises if the deny key is used as a group
