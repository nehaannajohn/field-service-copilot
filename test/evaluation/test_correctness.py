from evaluation.correctness import answer_text, key_point_score, verdict
from evaluation.run_eval import summarise


def grades(points, constraints=()):
    return {"key_points": [{"verdict": v} for v in points], "constraints": [{"verdict": v} for v in constraints]}


def test_all_points_present_is_correct():
    assert verdict(grades(["present", "present"], ["respected"])) == "correct"


def test_missing_or_partial_point_is_partially_correct():
    assert verdict(grades(["present", "missing"])) == "partially_correct"
    assert verdict(grades(["present", "partial"])) == "partially_correct"


def test_contradiction_or_violated_constraint_is_incorrect():
    assert verdict(grades(["present", "contradicted"])) == "incorrect"
    assert verdict(grades(["present"], ["violated"])) == "incorrect"


def test_no_key_points_is_not_correct():
    assert verdict(grades([])) == "partially_correct"


def test_answer_text_is_summary_or_message():
    answered = {"status": "answered", "summary": [{"sentence": "A.", "sources": ["S1"]}, {"sentence": "B.", "sources": []}]}
    assert answer_text(answered) == "A.\nB."
    assert answer_text({"status": "no_permitted_source", "message": "No document you have access to covers this."}) \
        == "No document you have access to covers this."


def test_key_point_score_counts_present_only():
    assert key_point_score(grades(["present", "partial", "missing", "present"])) == 0.5
    assert key_point_score(grades([])) is None


def test_micro_and_macro_scores():
    rows = [{"verdict": "correct", "key_points_present": 1, "key_points_total": 1, "key_point_score": 1.0},
            {"verdict": "partially_correct", "key_points_present": 1, "key_points_total": 3, "key_point_score": 1 / 3}]
    s = summarise(rows)
    assert s["micro_key_point_score"] == 0.5          # 2 of 4 points
    assert s["macro_key_point_score"] == 0.667        # mean of 1.0 and 0.333
