"""Command line: copilot ingest [files...] | copilot ask --user USER [--trace] QUESTION"""
import argparse
import json

from common.config import PROJECT_ROOT
from evaluation.run_eval import run_eval
from offline_pipeline.ingest import ingest
from online_query.pipeline import run_query, show


def print_trace(result: dict) -> None:
    print("\n--- trace ---")
    for event in result["trace"]["events"]:
        print(f"[{event['stage']}] {event['seconds']:.1f}s")
        print("  inputs: ", json.dumps(event["inputs"], ensure_ascii=False)[:300])
        print("  outputs:", json.dumps(event["outputs"], ensure_ascii=False)[:600])
    print("--- end trace ---\n")


def main() -> None:
    parser = argparse.ArgumentParser(prog="copilot")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = commands.add_parser("ingest", help="ingest the corpus, or only the given files (paths under data/)")
    ingest_cmd.add_argument("files", nargs="*")

    ask = commands.add_parser("ask", help="answer a question for a user")
    ask.add_argument("--user", required=True, help="user id from users.json, e.g. u03")
    ask.add_argument("--trace", action="store_true", help="print every pipeline stage")
    ask.add_argument("question")

    ev = commands.add_parser("eval", help="run the correctness eval on a question set")
    ev.add_argument("--set", default="data/eval/eval_questions.json",
                    help="questions file, relative to the project root")

    args = parser.parse_args()
    if args.command == "ingest":
        print(json.dumps(ingest(set(args.files) or None)["summary"], indent=2))
    elif args.command == "ask":
        result = run_query(args.question, args.user)
        if args.trace:
            print_trace(result)
        show(result)
    elif args.command == "eval":
        run_eval(PROJECT_ROOT / args.set)


if __name__ == "__main__":
    main()
