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
            present = sum(k["verdict"] == "present" for k in judgement["key_points"])
            row = {"id": q["id"], "user_id": q["user_id"], "verdict": judgement["verdict"], "status": result["status"],
                   "key_points_present": present, "key_points_total": len(judgement["key_points"]),
                   "key_point_score": judgement["key_point_score"]}
            detail = {"question": q, "result": result, "judgement": judgement}
        except Exception as e:   # one failing question doesn't stop the run
            row = {"id": q["id"], "user_id": q["user_id"], "verdict": "error", "status": f"{type(e).__name__}: {e}"}
            detail = {"question": q, "error": row["status"]}
        row["seconds"] = round(time.time() - start, 1)
        (out_dir / f"{q['id']}.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False))
        rows.append(row)
        points = f"{row.get('key_points_present', '-')}/{row.get('key_points_total', '-')}"
        print(f"{q['id']}  {row['verdict']:18s} {points:>6s} {row['status'][:40]:40s} {row['seconds']:5.1f}s", flush=True)

    summary = summarise(rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n{summary['correct']} of {len(rows)} correct  {summary['by_verdict']}"
          f"\nKey points: micro {summary['micro_key_point_score']:.0%} ({summary['key_points_present']}/"
          f"{summary['key_points_total']}), macro {summary['macro_key_point_score']:.0%}\nResults: {out_dir}")
    return summary


def summarise(rows: list[dict]) -> dict:
    """Verdict counts, plus the key-point score two ways:
    micro = all present points / all points (every key point weighs the same);
    macro = mean of per-question scores (every question weighs the same)."""
    counts = Counter(r["verdict"] for r in rows)
    scored = [r for r in rows if r.get("key_point_score") is not None]
    present = sum(r["key_points_present"] for r in scored)
    total = sum(r["key_points_total"] for r in scored)
    return {"questions": len(rows), "correct": counts["correct"], "by_verdict": dict(counts),
            "key_points_present": present, "key_points_total": total,
            "micro_key_point_score": round(present / total, 3) if total else None,
            "macro_key_point_score": round(sum(r["key_point_score"] for r in scored) / len(scored), 3) if scored else None,
            "rows": rows}
