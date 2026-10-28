"""Work order draft: one model call fills the Work Order Writing Guide fields from the verified claims."""
from common.access import certifications
from common.llm import structured
from online_query.compose import number_sources

INSTRUCTIONS = """You draft a work order for a supervisor to approve, using only the verified claims given.

INPUT
- Question: the technician's question.
- Requested by: the technician's user id.
- Technician certifications held: the certifications this technician holds.
- Reason: why the answer said a work order is needed.
- Claims: the verified claims, each with its sources (S1, S2, ...).

OUTPUT
- asset_id: the asset ID (e.g. FRS-P-0031) named in the question or a claim, or null if neither names one.
- fault_code: the fault code exactly as written in the question or a claim (e.g. E-31), or null.
- summary: one line: what is wrong and what is proposed.
- work_steps: the steps expected, in order. Refer to procedures by document number; never copy their steps.
- parts: part numbers and quantities stated in the claims; empty if none.
- certification_required: every certification the work needs: "HV", "Refrigerant", "Confined space",
  or "None" alone.
- estimated_duration_h: hours on site if a claim states it, otherwise null.
- priority: "Low", "Medium", "High" or "Critical", following the priority rules stated in the claims;
  null if no claim supports a priority.
- campaign_code: the OEM campaign code if a claim gives one, otherwise null.
- sources: the source ids of the claims the work order uses.

RULES
1. asset_id and fault_code come from the question or the claims; every other field comes only from the claims.
   A field nothing supports is null (or empty for lists).
2. Never invent part numbers, codes or IDs."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["asset_id", "fault_code", "summary", "work_steps", "parts", "certification_required",
                 "estimated_duration_h", "priority", "campaign_code", "sources"],
    "properties": {
        "asset_id": {"type": ["string", "null"]},
        "fault_code": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "work_steps": {"type": "array", "items": {"type": "string"}},
        "parts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["part_number", "qty"],
            "properties": {"part_number": {"type": "string"}, "qty": {"type": ["integer", "null"]}}}},
        "certification_required": {"type": "array", "items": {
            "type": "string", "enum": ["None", "HV", "Refrigerant", "Confined space"]}},
        "estimated_duration_h": {"type": ["number", "null"]},
        "priority": {"type": ["string", "null"], "enum": ["Low", "Medium", "High", "Critical", None]},
        "campaign_code": {"type": ["string", "null"]},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
}


def draft_work_order(question: str, user_id: str, claims_output: dict, verification: dict) -> dict | None:
    """A work order draft when the answer said one is needed and at least one claim survived verification.
    Uses the same S1, S2, ... numbering as the summary, so its sources match the evidence table."""
    results = verification["results"]
    kept = [c for c in claims_output["claims"] if results.get(c["id"], {}).get("kept")]
    if not claims_output["work_order_needed"] or not kept:
        return None
    sources = number_sources(claims_output["claims"], results)
    held = ", ".join(certifications(user_id)) or "none"
    claim_lines = "\n".join(
        f"- {c['text']} | sources: {', '.join(sources[x] for x in results[c['id']]['citations'])}" for c in kept)
    prompt = (f"Question: {question}\nRequested by: {user_id}\n"
              f"Technician certifications held: {held}\n"
              f"Reason: {claims_output['work_order_reason']}\n\nClaims:\n{claim_lines}")
    draft = structured("work_order", prompt, SCHEMA, "work_order", instructions=INSTRUCTIONS)
    return draft | {"requested_by": user_id, "reason": claims_output["work_order_reason"]}
