"""Correctness judge: grade an answer against the reference answer's key points and constraints."""
from common.llm import structured

INSTRUCTIONS = """You grade a field-service copilot's answer against a reference answer written by experts.

INPUT
- Question: the question the technician asked.
- Reference answer: the expert answer. It states key points, and may state constraints on the answer
  (for example "The answer must not contain any reset steps", or "Answering with X is wrong").
- Copilot answer: the copilot's response: its summary sentences, or its message when it could not answer.

OUTPUT
- key_points: every key point of the reference answer, each with:
  - point: the key point, in a few words;
  - verdict: "present", "partial", "missing" or "contradicted";
  - reason: one sentence pointing to what the copilot answer says (or does not say).
- constraints: every constraint the reference answer states, each with:
  - constraint: the constraint, in a few words;
  - verdict: "respected" or "violated";
  - reason: one sentence.
  Empty if the reference states none.

RULES
1. A key point is a fact, instruction or conclusion the reference gives. Split the reference into its key points;
   do not merge several facts into one point.
2. "present": the copilot answer states it, in any wording. "partial": it states part of it, or states it
   less precisely (for example a value without its unit or condition). "missing": it does not state it.
   "contradicted": it states something incompatible with it.
3. Grade only against the reference. Information in the copilot answer that the reference does not mention is
   not an error, unless it contradicts a key point or violates a constraint.
4. If the reference says no source covers the question, the key point is that the copilot says so; giving a
   substantive answer instead contradicts it."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["key_points", "constraints"],
    "properties": {
        "key_points": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["point", "verdict", "reason"],
            "properties": {
                "point": {"type": "string"},
                "verdict": {"type": "string", "enum": ["present", "partial", "missing", "contradicted"]},
                "reason": {"type": "string"}}}},
        "constraints": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["constraint", "verdict", "reason"],
            "properties": {
                "constraint": {"type": "string"},
                "verdict": {"type": "string", "enum": ["respected", "violated"]},
                "reason": {"type": "string"}}}},
    },
}


def answer_text(result: dict) -> str:
    """What the technician reads: the summary sentences, or the message when the copilot could not answer."""
    if result["status"] != "answered":
        return result["message"]
    return "\n".join(s["sentence"] for s in result["summary"])


def verdict(judgement: dict) -> str:
    """correct: every key point present and no constraint violated.
    incorrect: any key point contradicted or any constraint violated.
    partially_correct: otherwise (some point partial or missing)."""
    points = [k["verdict"] for k in judgement["key_points"]]
    constraints = [c["verdict"] for c in judgement["constraints"]]
    if "contradicted" in points or "violated" in constraints:
        return "incorrect"
    if points and all(p == "present" for p in points):
        return "correct"
    return "partially_correct"


def judge(question: str, reference: str, result: dict) -> dict:
    """One judge call; the verdict is computed in code from the per-point grades."""
    prompt = (f"Question: {question}\n\nReference answer:\n{reference}\n\n"
              f"Copilot answer:\n{answer_text(result)}")
    judgement = structured("judge", prompt, SCHEMA, "correctness", instructions=INSTRUCTIONS)
    return judgement | {"verdict": verdict(judgement)}
