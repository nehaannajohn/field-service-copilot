from common.access import certifications
from online_query.claims import SCHEMA, format_certifications


def objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            yield from objects(value)


def test_schema_is_strict_mode_compatible():
    for obj in objects(SCHEMA):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_certifications_use_the_configured_prefix():
    assert set(certifications("u02")) == {"cert-hv"}            # Daniel
    assert certifications("u03") == {}                          # Priya
    assert set(certifications("u08")) == {"cert-hv", "cert-confined-space"}


def test_certification_list_marks_held_and_not_held():
    text = format_certifications("u03")
    assert "cert-hv: High-voltage electrical certification (VFD cabinets) — NOT held" in text
    assert "HELD" not in text.replace("NOT held", "")
