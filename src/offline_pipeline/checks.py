"""Checks on a parsed part: completeness, transformations consistent with the output, English filled in."""
import csv
import io
import json
from pathlib import Path

from offline_pipeline.inputs import ModelInput
from offline_pipeline.parse import parse_part

class IncompleteParse(Exception):
    """The model's output for a part fails a check, after one retry."""


def expected_records(suffix: str, model_input: ModelInput) -> int | None:
    """Number of records sent in a CSV or JSON part; None for other inputs."""
    text = model_input.content.get("text")
    if text is None:
        return None
    if suffix == ".csv":
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|")
        return len(list(csv.reader(io.StringIO(text), dialect))) - 1
    if suffix == ".json":
        data = json.loads(text)
        return len(data) if isinstance(data, list) else None
    return None


def completeness_problem(suffix: str, model_input: ModelInput, result: dict) -> str | None:
    units = result["units"]
    expected = expected_records(suffix, model_input)
    if expected is not None:
        got = sum(1 for u in units if u["unit_type"] in ("record", "message"))
        return None if got >= expected else f"expected at least {expected} records, got {got}"
    return None   # documents (PDF, DOCX, HTML, EML, text): no exact count to compare against


def transformation_problem(result: dict) -> str | None:
    """The listed transformations must match what the output shows. Run before English is filled in."""
    applied, units = set(result["transformations_applied"]), result["units"]
    translated = [u for u in units if u["text_en"] is not None]
    if "translation" in applied and not translated:
        return "translation listed but no unit has text_en"
    if translated and "translation" not in applied:
        return "units have text_en but translation is not listed"
    if any(u["lang"] != "en" and u["text_en"] is None for u in units):
        return "a non-English unit has no text_en"
    return None


def fill_english(result: dict) -> None:
    for unit in result["units"]:
        if unit["text_en"] is None:
            unit["text_en"] = unit["text_original"]


def parse_checked(path: Path, model_input: ModelInput) -> dict:
    """Parse one part and retry once if any check fails; then fill English text for English units."""
    suffix = path.suffix.lower()
    for _ in (1, 2):
        result = parse_part(path, model_input)
        problem = completeness_problem(suffix, model_input, result) or transformation_problem(result)
        if problem is None:
            break
    else:
        raise IncompleteParse(f"{path.name} part {model_input.part}: {problem}")
    fill_english(result)
    return result
