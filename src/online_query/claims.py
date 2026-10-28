"""Claims step: one model call turns the question and retrieved chunks into cited claims and a follow-up decision."""
from common.access import certifications, group_descriptions
from common.config import load_config
from common.llm import structured
from online_query.retrieve import Retrieved

TOPICS = ("industrial equipment service: equipment faults and alarms, troubleshooting, maintenance and repair "
          "procedures, parts, technical specifications, safety and certification requirements, service history, "
          "cases and work orders")

INSTRUCTIONS = f"""You answer a field technician's question using only the document chunks provided.

INPUT
- Question: the technician's question.
- Technician certifications: every certification that exists, each with its description and whether this
  technician holds it (HELD or NOT held).
- Chunks: the documents retrieved for this technician. Each chunk has:
  - chunk_id: its identifier, used for citations;
  - a header: document title, revision, and section or record;
  - Type, Revision, Date: document metadata ("unknown" when not stated);
  - text: the chunk's content in English.
  The list may be empty.

OUTPUT
- status: "answered", "no_permitted_source" or "out_of_domain".
- claims: short, self-contained factual statements that answer the question. Each has an id ("c1", "c2", ...),
  its text, and citations: the chunk_id of every chunk that states it.
- work_order_needed: true if the fix needs follow-up, otherwise false.
- work_order_reason: the main reason for the follow-up, or null when work_order_needed is false.

RULES, applied in this order
1. If the chunk list is empty, or no chunk relates to {TOPICS}:
   status = "out_of_domain", claims = [], work_order_needed = false, work_order_reason = null.
2. Otherwise, if the chunks do not answer the question:
   status = "no_permitted_source", claims = [], work_order_needed = false, work_order_reason = null.
   A chunk about a different model, asset or topic does not answer the question, even if it looks similar.
3. Otherwise: status = "answered", and
   a. Write the claims using only what the chunks state; never use outside knowledge.
      Every claim cites at least one chunk_id.
   b. If the chunks say the work needs a certification the technician does NOT hold, include a claim that the
      work needs that certification, and do not include the steps of the certified work.
   c. If the fix needs parts, a certification the technician does not hold, an OEM campaign, a specialist or
      a return visit, or the fault is a repeat: work_order_needed = true and work_order_reason = the main
      reason. Otherwise: work_order_needed = false and work_order_reason = null."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "claims", "work_order_needed", "work_order_reason"],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["answered", "no_permitted_source", "out_of_domain"],
            "description": "Set by rules 1-3, applied in order.",
        },
        "claims": {
            "type": "array",
            "description": "Empty unless status is 'answered'.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text", "citations"],
                "properties": {
                    "id": {"type": "string", "description": "c1, c2, ... in order."},
                    "text": {"type": "string", "description": "One self-contained factual statement."},
                    "citations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "chunk_id of every chunk that states this claim; at least one.",
                    },
                },
            },
        },
        "work_order_needed": {"type": "boolean", "description": "False unless status is 'answered' and rule 3c applies."},
        "work_order_reason": {
            "type": ["string", "null"],
            "enum": ["parts", "certification_not_held", "campaign", "specialist", "return_visit", "repeat_fault", None],
            "description": "The main reason when work_order_needed is true; otherwise null.",
        },
    },
}


def format_chunks(chunks: list[Retrieved]) -> str:
    return "\n\n".join(
        f"[chunk_id: {c.chunk_id}]\n{c.header}\nType: {c.doc_type} | Revision: {c.revision} | Date: {c.effective_date}\n"
        f"{c.text_en}"
        for c in chunks
    )


def format_certifications(user_id: str) -> str:
    held = certifications(user_id)
    prefix = load_config()["access"]["certification_prefix"]
    all_certs = {g: d for g, d in group_descriptions().items() if g.startswith(prefix)}
    return "\n".join(f"- {g}: {d} — {'HELD' if g in held else 'NOT held'}" for g, d in all_certs.items())


def generate_claims(question: str, user_id: str, chunks: list[Retrieved]) -> dict:
    prompt = (f"Technician certifications:\n{format_certifications(user_id)}\n\n"
              f"Question: {question}\n\nChunks:\n{format_chunks(chunks) if chunks else '(none)'}")
    return structured("answer", prompt, SCHEMA, "claims", instructions=INSTRUCTIONS)
