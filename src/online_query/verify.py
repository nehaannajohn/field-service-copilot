"""Verify step: check every claim against every cited chunk in one model call, then derive each claim's result."""
from common.llm import structured
from online_query.retrieve import Retrieved

INSTRUCTIONS = """You check factual claims against source document chunks.

INPUT
- Question: the technician's question the claims answer.
- Claims: each has a claim_id and its text.
- Chunks: each has a chunk_id, a header, and its text in English.

OUTPUT
- cells: exactly one cell for every (claim, chunk) pair, so (number of claims) x (number of chunks) cells.
  Each cell has:
  - claim_id, chunk_id: the pair being checked;
  - verdict: "supports", "contradicts" or "irrelevant";
  - evidence: the exact words copied from the chunk that support or contradict the claim, or null.

RULES
1. "supports": the chunk states the claim, or states facts from which the claim follows directly.
   Numbers, units, part numbers, codes and model names must match exactly.
2. "contradicts": the chunk states something about the same subject that cannot be true at the same time as
   the claim (for example a different torque value for the same pump and serial range).
3. "irrelevant": the chunk neither supports nor contradicts the claim.
4. evidence is a verbatim quote from the chunk for "supports" and "contradicts", and null for "irrelevant".
5. Judge each pair only on that chunk's text. Do not use outside knowledge."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cells"],
    "properties": {
        "cells": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim_id", "chunk_id", "verdict", "evidence"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "chunk_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["supports", "contradicts", "irrelevant"]},
                    "evidence": {"type": ["string", "null"],
                                 "description": "Verbatim quote from the chunk; null when irrelevant."},
                },
            },
        },
    },
}

class IncompleteVerification(Exception):
    """The verifier did not return a cell for every (claim, chunk) pair, after one retry."""


def cited_chunks(claims: list[dict], retrieved: list[Retrieved]) -> list[Retrieved]:
    """The union of chunks cited anywhere in the answer, in retrieval order. Unknown ids are ignored here
    and reported per claim by the citation check."""
    cited = {cid for c in claims for cid in c["citations"]}
    return [r for r in retrieved if r.chunk_id in cited]


def verify_matrix(question: str, claims: list[dict], chunks: list[Retrieved]) -> list[dict]:
    """One verifier call; retried once if any (claim, chunk) pair is missing."""
    prompt = (f"Question: {question}\n\nClaims:\n" + "\n".join(f"[{c['id']}] {c['text']}" for c in claims) +
              "\n\nChunks:\n" + "\n\n".join(f"[chunk_id: {c.chunk_id}]\n{c.header}\n{c.text_en}" for c in chunks))
    expected = {(c["id"], ch.chunk_id) for c in claims for ch in chunks}
    for _ in (1, 2):
        cells = structured("verifier", prompt, SCHEMA, "verification", instructions=INSTRUCTIONS)["cells"]
        if expected <= {(cell["claim_id"], cell["chunk_id"]) for cell in cells}:
            return cells
    raise IncompleteVerification(f"missing pairs: {sorted(expected - {(c['claim_id'], c['chunk_id']) for c in cells})[:5]}")


def derive_results(claims: list[dict], chunks: list[Retrieved], cells: list[dict], permitted_ids: set[str]) -> dict:
    """Per-claim result from its row of the matrix, plus the code checks."""
    by_id = {ch.chunk_id: ch for ch in chunks}
    results = {}
    for claim in claims:
        row = [cell for cell in cells if cell["claim_id"] == claim["id"] and cell["chunk_id"] in by_id]
        real = [c for c in row if c["verdict"] != "irrelevant"]
        supports = [c["chunk_id"] for c in real if c["verdict"] == "supports"]
        contradicts = [c["chunk_id"] for c in real if c["verdict"] == "contradicts"]

        if supports and contradicts:
            status = "sources_disagree"
        elif supports:
            status = "supported" if set(supports) & set(claim["citations"]) else "supported_citation_corrected"
        elif contradicts:
            status = "contradicted"
        else:
            status = "unsupported"

        failed = [f"citation not permitted: {cid}" for cid in claim["citations"] if cid not in permitted_ids]
        if failed and status != "contradicted":
            status = "unsupported"

        results[claim["id"]] = {
            "status": status,
            "citations": supports,                 # the supporting chunks become the claim's citations
            "contradicting": contradicts,
            "evidence": {c["chunk_id"]: c["evidence"] for c in real},
            "failed_checks": failed,
            "kept": status in ("supported", "supported_citation_corrected", "sources_disagree"),
        }
    return results


def verify(question: str, claims_output: dict, retrieved: list[Retrieved]) -> dict:
    """Verify the claims step's output. Returns the raw matrix and the per-claim results (both empty when
    there are no claims)."""
    claims = claims_output["claims"]
    if claims_output["status"] != "answered" or not claims:
        return {"cells": [], "results": {}}
    chunks = cited_chunks(claims, retrieved)
    cells = verify_matrix(question, claims, chunks) if chunks else []
    return {"cells": cells, "results": derive_results(claims, chunks, cells, {r.chunk_id for r in retrieved})}
