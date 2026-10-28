"""Compose step: summarise the verified claims into the answer, with sources for each sentence."""
from common.llm import structured
from online_query.retrieve import Retrieved

INSTRUCTIONS = """You summarise verified claims into the answer for a field technician.

INPUT
- Question: the technician's question.
- Claims: each has its text and its sources (S1, S2, ...). A disputed claim also lists the sources that
  contradict it.

OUTPUT
- summary: the answer as a list of sentences, in reading order. Each has its text and the sources of the
  claims it uses.

RULES
1. Use only the claims given; add nothing else.
2. Every sentence lists at least one source.
3. If a claim is disputed, say that the sources disagree, and list both its supporting and contradicting sources.
4. Be brief but complete: combine related claims into one sentence, and keep every claim;
   no introduction, no summary, no repetition."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary"],
    "properties": {
        "summary": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["sentence", "sources"],
                "properties": {
                    "sentence": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def number_sources(claims: list[dict], results: dict) -> dict[str, str]:
    """chunk_id -> S1, S2, ... in order of first use by the kept claims (supporting, then contradicting)."""
    ids: dict[str, str] = {}
    for claim in claims:
        r = results[claim["id"]]
        if r["kept"]:
            for chunk_id in r["citations"] + r["contradicting"]:
                ids.setdefault(chunk_id, f"S{len(ids) + 1}")
    return ids


def location(chunk: Retrieved) -> str:
    """Where in the document the chunk is: page and section, or record ID, plus sender and date for messages."""
    loc = chunk.locator
    parts = []
    if loc.get("page"):
        parts.append(f"p.{loc['page']}")
    if loc.get("section_path"):
        parts.append(" › ".join(loc["section_path"]))
    elif loc.get("record_id"):
        parts.append(loc["record_id"])
    if loc.get("sender") or loc.get("date"):
        parts.append(", ".join(x for x in (loc.get("sender"), loc.get("date")) if x))
    return " · ".join(parts)


def chunk_status(chunk_id: str, verification: dict) -> tuple[str, str | None]:
    """(status, evidence) for a chunk across the kept claims: Contradicted if it contradicts any, else Supported."""
    kept = {cid for cid, r in verification["results"].items() if r["kept"]}
    cells = [c for c in verification["cells"] if c["chunk_id"] == chunk_id and c["claim_id"] in kept]
    for verdict, status in (("contradicts", "Contradicted"), ("supports", "Supported")):
        hit = next((c for c in cells if c["verdict"] == verdict), None)
        if hit:
            return status, hit["evidence"]
    return "Supported", None


def evidence_table(summary: list[dict], sources: dict[str, str], retrieved: list[Retrieved],
                   verification: dict) -> list[dict]:
    """One row per (sentence, source): the source's chunk, document details and verification status."""
    by_id = {r.chunk_id: r for r in retrieved}
    chunk_of = {s: chunk_id for chunk_id, s in sources.items()}
    rows = []
    for item in summary:
        for s in item["sources"]:
            if s not in chunk_of:      # an id the model invented: no chunk to show
                continue
            chunk = by_id[chunk_of[s]]
            status, evidence = chunk_status(chunk.chunk_id, verification)
            rows.append({"sentence": item["sentence"], "source": s, "chunk_id": chunk.chunk_id,
                         "title": chunk.doc_title, "location": location(chunk), "doc_type": chunk.doc_type,
                         "revision": chunk.revision, "date": chunk.effective_date,
                         "status": status, "evidence": evidence})
    return rows


def compose(question: str, claims: list[dict], verification: dict, retrieved: list[Retrieved]) -> dict:
    """Summary sentences with sources, and the evidence table built from them."""
    results = verification["results"]
    kept = [c for c in claims if results.get(c["id"], {}).get("kept")]
    if not kept:
        return {"summary": [], "evidence": []}
    sources = number_sources(claims, results)
    claim_lines = []
    for c in kept:
        r = results[c["id"]]
        line = f"- {c['text']} | sources: {', '.join(sources[x] for x in r['citations'])}"
        if r["contradicting"]:
            line += f" | contradicted by: {', '.join(sources[x] for x in r['contradicting'])}"
        claim_lines.append(line)
    prompt = f"Question: {question}\n\nClaims:\n" + "\n".join(claim_lines)

    summary = structured("answer", prompt, SCHEMA, "summary", instructions=INSTRUCTIONS)["summary"]
    return {"summary": summary, "evidence": evidence_table(summary, sources, retrieved, verification)}
