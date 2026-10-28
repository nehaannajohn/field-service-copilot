"""Correctness eval: run each question through the copilot, judge it against its reference, report the score."""
import json
import time
from collections import Counter
from pathlib import Path

from common.config import load_config
from evaluation.correctness import judge
from online_query.pipeline import run_query


def run_eval(questions_file: Path) -> dict:
    questions = json.loads(questions_file.read_text())
    out_dir = load_config()["paths"]["eval_results_dir"] / f"{questions_file.stem}_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for q in questions:
        start = time.time()
        try:
            result = run_query(q["question"], q["user_id"])
            judgement = judge(q["question"], q["reference_answer"], result)
            row = {"id": q["id"], "user_id": q["user_id"], "verdict": judgement["verdict"], "status": result["status"]}
            detail = {"question": q, "result": result, "judgement": judgement}
        except Exception as e:   # one failing question doesn't stop the run
            row = {"id": q["id"], "user_id": q["user_id"], "verdict": "error", "status": f"{type(e).__name__}: {e}"}
            detail = {"question": q, "error": row["status"]}
        row["seconds"] = round(time.time() - start, 1)
        (out_dir / f"{q['id']}.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False))
        rows.append(row)
        print(f"{q['id']}  {row['verdict']:18s} {row['status'][:40]:40s} {row['seconds']:5.1f}s", flush=True)

    counts = Counter(r["verdict"] for r in rows)
    summary = {"questions": len(rows), "correct": counts["correct"], "by_verdict": dict(counts), "rows": rows}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n{counts['correct']} of {len(rows)} correct  {dict(counts)}\nResults: {out_dir}")
    return summary
