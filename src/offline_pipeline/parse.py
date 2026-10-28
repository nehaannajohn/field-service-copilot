"""One model call per input part: structure, clean, OCR, translate and extract metadata."""
from pathlib import Path

from common.llm import structured
from offline_pipeline.inputs import ModelInput

TRANSFORMATIONS = ["ocr", "translation", "layout_cleanup", "boilerplate_removal",
                   "structure_inference", "thread_grouping", "metadata_extraction"]

NULLABLE_STRING = {"type": ["string", "null"]}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["metadata", "transformations_applied", "units"],
    "properties": {
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": ["doc_type", "doc_number", "revision", "effective_date", "evidence"],
            "properties": {
                "doc_type": {"type": "string"},
                "doc_number": {"type": "string"},
                "revision": {"type": "string"},
                "effective_date": {"type": "string"},
                "evidence": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["doc_type", "doc_number", "revision", "effective_date"],
                    "properties": {k: NULLABLE_STRING for k in
                                   ["doc_type", "doc_number", "revision", "effective_date"]},
                },
            },
        },
        "transformations_applied": {"type": "array", "items": {"type": "string", "enum": TRANSFORMATIONS}},
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["unit_type", "locator", "parent_id", "lang", "text_original", "text_en"],
                "properties": {
                    "unit_type": {"type": "string", "enum": ["section", "message", "record"]},
                    "locator": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["page", "section_path", "record_id", "sender", "date"],
                        "properties": {
                            "page": {"type": ["integer", "null"]},
                            "section_path": {"type": "array", "items": {"type": "string"}},
                            "record_id": NULLABLE_STRING,
                            "sender": NULLABLE_STRING,
                            "date": NULLABLE_STRING,
                        },
                    },
                    "parent_id": NULLABLE_STRING,
                    "lang": {"type": "string"},
                    "text_original": {"type": "string"},
                    "text_en": NULLABLE_STRING,
                },
            },
        },
    },
}

INSTRUCTIONS = """You convert one exported business document into clean, structured, English text for a search index.

1. Structure. Split the document into units:
   - section: a part of a manual, procedure, wiki page or report, with its page number and heading path;
   - message: one email or chat message, with sender and date;
   - record: one row or object of a table or data export, with its ID and date. If a record replies to
     or belongs to another record, set parent_id to that record's ID.
     Write each record as "field: value" lines, using the column or key names. A header row is not a unit.
   A section includes its lists, steps, definitions and tables; do not split them into separate units.
   Use record only for rows of tables or data exports that make up the whole document.
2. Clean. Remove layout noise, repeated page headers and footers, and email disclaimers and signatures.
   Never summarize, shorten or drop content. Keep every table row.
3. OCR. If a page is an image, read its text.
4. Translate. If a unit is not in English, put the English translation in text_en; otherwise text_en is null.
   Copy codes, part numbers, IDs, serial numbers, numbers and units exactly as written.
   text_original is always the cleaned text in its original language.
5. Metadata. Fill doc_type, doc_number, revision and effective_date only from what the document states;
   otherwise "unknown". effective_date is the issue, edition, effective or last-modified date the document
   states. For each value, quote the exact text it came from in evidence (null if unknown).
6. transformations_applied lists every transformation you applied, using only the allowed values."""


def parse_part(path: Path, model_input: ModelInput) -> dict:
    """Send one input part to the ingest model and return the structured result."""
    header = {"type": "input_text",
              "text": f"File: {path.name}. Part {model_input.part} of {model_input.total_parts}."}
    return structured(
        "ingest",
        input=[{"role": "user", "content": [header, model_input.content]}],
        schema=SCHEMA,
        schema_name="document",
        instructions=INSTRUCTIONS,
    )
