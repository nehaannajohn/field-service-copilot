from online_query.work_order import SCHEMA, draft_work_order

CLAIMS = {"status": "answered", "work_order_needed": True, "work_order_reason": "certification_not_held",
          "claims": [{"id": "c1", "text": "E-31 needs an HV-certified technician", "citations": ["k1"]}]}


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


def test_no_draft_when_not_needed():
    verification = {"results": {"c1": {"kept": True, "citations": ["k1"], "contradicting": []}}, "cells": []}
    assert draft_work_order("q", "u03", {**CLAIMS, "work_order_needed": False}, verification) is None


def test_no_draft_when_no_claim_survived_verification():
    verification = {"results": {"c1": {"kept": False, "citations": [], "contradicting": []}}, "cells": []}
    assert draft_work_order("q", "u03", CLAIMS, verification) is None
