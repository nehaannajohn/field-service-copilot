"""Query runner: retrieve -> claims -> verify -> compose -> work order draft, assembled into one result."""
import json
import shutil
import textwrap
import time
from dataclasses import asdict

from common.config import load_config
from common.trace import Trace
from offline_pipeline.index import connect
from online_query.claims import generate_claims
from online_query.compose import compose
from online_query.retrieve import retrieve
from online_query.verify import verify
from online_query.work_order import draft_work_order

MESSAGES = {
    "out_of_domain": "This question isn't about equipment service, so I can't help with it here.",
    "no_permitted_source": "No document you have access to covers this.",
}


def run_query(question: str, user_id: str) -> dict:
    trace = Trace()
    conn = connect()
    with trace.stage("retrieve", question=question, user_id=user_id) as ev:
        retrieved = retrieve(conn, question, user_id)
        ev.outputs = {"chunks": [(r.chunk_id, r.doc_title, r.header) for r in retrieved]}
    with trace.stage("claims") as ev:
        claims_output = generate_claims(question, user_id, retrieved)
        ev.outputs = claims_output
    with trace.stage("verify") as ev:
        verification = verify(question, claims_output, retrieved)
        ev.outputs = {cid: r["status"] for cid, r in verification["results"].items()}
    with trace.stage("compose") as ev:
        answer = compose(question, claims_output["claims"], verification, retrieved)
        ev.outputs = {"sentences": len(answer["summary"])}
    with trace.stage("work_order") as ev:
        work_order = draft_work_order(question, user_id, claims_output, verification)
        ev.outputs = {"drafted": work_order is not None}

    dropped = [c["text"] for c in claims_output["claims"]
               if not verification["results"].get(c["id"], {}).get("kept")]
    status = claims_output["status"] if answer["summary"] else (
        "out_of_domain" if claims_output["status"] == "out_of_domain" else "no_permitted_source")
    return {
        "question": question, "user_id": user_id, "status": status,
        "message": MESSAGES.get(status),
        "summary": answer["summary"], "evidence": answer["evidence"],
        "dropped_claims": dropped,          # claims rejected by verify; kept for the trace, not displayed
        "work_order": work_order,
        "trace": trace.to_dict(),
        "retrieved": [asdict(r) for r in retrieved],
    }


COLUMNS = [("Sentence", 0.24, 20), ("Src", 0.05, 4), ("Status", 0.10, 12), ("Document", 0.20, 16),
           ("Location", 0.22, 16), ("Rev", 0.06, 4), ("Date", 0.13, 10)]   # (name, share of width, minimum)


def table(rows: list[list[str]]) -> str:
    """A bordered table that fits the terminal width; long cells wrap inside their column."""
    width = max(80, shutil.get_terminal_size().columns) - 3 * len(COLUMNS) - 1
    widths = [max(len(name), minimum, int(width * share)) for name, share, minimum in COLUMNS]
    line = lambda l, m, r: l + m.join("─" * (w + 2) for w in widths) + r

    def render(cells):
        wrapped = [textwrap.wrap(str(c), w) or [""] for c, w in zip(cells, widths)]
        return ["│" + "│".join(f" {(col[i] if i < len(col) else ''):<{w}} " for col, w in zip(wrapped, widths)) + "│"
                for i in range(max(len(col) for col in wrapped))]

    out = [line("┌", "┬", "┐"), *render([name for name, *_ in COLUMNS]), line("├", "┼", "┤")]
    for i, row in enumerate(rows):
        if i:
            out.append(line("├", "┼", "┤"))
        out += render(row)
    return "\n".join(out + [line("└", "┴", "┘")])


def evidence_rows(evidence: list[dict]) -> list[list[str]]:
    rows, previous = [], None
    for r in evidence:
        mark = "✓" if r["status"] == "Supported" else "✗"
        blank = lambda v: "" if v == "unknown" else v
        rows.append(["" if r["sentence"] == previous else r["sentence"], f"{r['source']} {mark}", r["status"],
                     r["title"], r["location"], blank(r["revision"]), blank(r["date"])])
        previous = r["sentence"]
    return rows


def render_answer(result: dict) -> str:
    """Summary with ✓/✗ source markers, then the evidence table, then the work order draft if there is one."""
    if result["status"] != "answered":
        return result["message"]
    status = {r["source"]: "✓" if r["status"] == "Supported" else "✗" for r in result["evidence"]}
    lines = [f"{s['sentence']} [{', '.join(f'{x} {status.get(x, chr(63))}' for x in s['sources'])}]"
             for s in result["summary"]]
    lines += ["", "Evidence:", table(evidence_rows(result["evidence"]))]
    if result["work_order"]:
        lines += ["", "Work order draft:", json.dumps(result["work_order"], indent=2, ensure_ascii=False)]
    return "\n".join(lines)


def submit_work_order(work_order: dict, approved: bool) -> str:
    """Approved: copy to the outbox. Rejected: discard. Returns the closing message."""
    if not approved:
        return "Work order discarded."
    outbox = load_config()["paths"]["outbox_dir"]
    outbox.mkdir(parents=True, exist_ok=True)
    wo_id = f"WO-{time.strftime('%Y%m%d-%H%M%S')}-{work_order['requested_by']}"
    (outbox / f"{wo_id}.json").write_text(json.dumps({"id": wo_id, **work_order}, indent=2, ensure_ascii=False))
    return f"Work order {wo_id} submitted for supervisor approval."


def show(result: dict) -> None:
    """Terminal output: the answer, then a yes/no approval prompt below the work order if there is one."""
    print(render_answer(result))
    if result["work_order"]:
        answer = input("\nApprove this work order? [y/n] ").strip().lower()
        print(submit_work_order(result["work_order"], approved=answer == "y"))
