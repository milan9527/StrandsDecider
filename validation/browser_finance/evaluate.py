"""Re-score saved evidence only; preserve raw results and document evaluator errata."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from common import save, stamp
from runner import summarize


def correct_cfpb(run, observation, expected):
    updated = copy.deepcopy(run)
    checks = {
        "url": expected["url_contains"].casefold() in observation["url"].casefold(),
        "heading": expected["heading"].casefold() in " ".join(observation["headings"]).casefold(),
        "body_terms": all(
            term.casefold() in observation["text"].casefold() for term in expected["body_terms"]
        ),
    }
    verified = all(checks.values())
    finished = (
        bool(run["steps"])
        and run["steps"][-1].get("action", {}).get("kind") == "finish"
        and run["steps"][-1].get("status") == "executed"
    )
    updated["raw_status"] = run["status"]
    updated["raw_success"] = run["success"]
    updated["corrected_final_check"] = {
        "passed": verified,
        "checks": checks,
        "url": observation["url"],
    }
    updated["success"] = verified and finished
    updated["goal_reached"] = run["goal_reached"] or verified
    if updated["success"]:
        updated["status"] = "completed"
    updated["evaluation_note"] = (
        "CFPB exact phrase corrected from '60 days' to '60 calendar days'; no model rerun or action change."
    )
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    folder = args.run
    plan = json.loads((folder / "plan.json").read_text())
    erratum = json.loads(Path("evaluation-erratum.json").read_text())
    source = Path(erratum["source_file"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == erratum["source_sha256"]
    finance = json.loads((folder / "finance-results.json").read_text())
    original = json.loads((folder / "browser-results.json").read_text())
    receipts = [json.loads(line) for line in (folder / "receipts.jsonl").read_text().splitlines()]
    expected = copy.deepcopy(
        next(t["expected"] for t in plan["browser"]["tasks"] if t["id"] == erratum["task_id"])
    )
    expected["body_terms"] = erratum["corrected"]
    scored = []
    for run in original:
        if run["task_id"] == erratum["task_id"]:
            observation_path = folder / "browser" / run["id"] / "final-observation.json"
            if observation_path.exists():
                run = correct_cfpb(run, json.loads(observation_path.read_text()), expected)
        scored.append(run)
    summary = summarize(finance, scored, receipts)
    summary["evaluation"] = {
        "scored_at": stamp(),
        "erratum": erratum,
        "raw_results_preserved": True,
        "additional_model_calls": 0,
        "changed_run_ids": [
            a["id"] for a, b in zip(scored, original, strict=True) if a["success"] != b["success"]
        ],
    }
    save(folder / "scored-browser-results.json", scored)
    save(folder / "scored-summary.json", summary)
    print(
        json.dumps(
            {
                k: {
                    "browser": summary["browser"][k]["success"],
                    "browser_total": summary["browser"][k]["total"],
                    "finance": summary["finance"][k]["correct"],
                    "finance_total": summary["finance"][k]["total"],
                    "models": summary["api"][k]["actual_models"],
                }
                for k in ("jev", "decider")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
