from offline_pipeline.parse import SCHEMA


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
