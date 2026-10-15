"""Check recorded evidence, accounting and identical-input finance pairs."""

import argparse
import hashlib
import json
from pathlib import Path

from common import digest, save, stamp
from runner import finance_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    folder = args.run
    plan = json.loads((folder / "plan.json").read_text())
    metadata = json.loads((folder / "run.json").read_text())
    receipts = [json.loads(s) for s in (folder / "receipts.jsonl").read_text().splitlines()]
    browsing = json.loads((folder / "browser-results.json").read_text())
    finance = json.loads((folder / "finance-results.json").read_text())
    assert metadata["status"] == "complete"
    assert len(receipts) == metadata["actual_calls"] <= plan["budget"]["total_max_calls"]
    assert len(finance) == plan["budget"]["finance_calls"]
    assert len(browsing) == len(plan["browser"]["tasks"]) * plan["browser"]["repeats"] * 2
    assert digest({k: v for k, v in plan.items() if k != "plan_sha256"}) == plan["plan_sha256"]
    for filename, checksum in metadata["code_sha256"].items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == checksum, filename
    for receipt in receipts:
        assert digest(receipt["input"]) == receipt["input_sha256"]
        assert receipt["attempt"] == 1 and not receipt["retry"]
        assert receipt["status"] == "ok"
    for case in plan["finance"]["cases"]:
        for variant in plan["finance"]["variants"]:
            pair = [
                r
                for r in receipts
                if r.get("case_id") == case["id"] and r.get("variant") == variant
            ]
            assert len(pair) == 2
            assert {r["provider"] for r in pair} == {"jev", "decider"}
            assert {r["input_sha256"] for r in pair} == {digest(finance_payload(case, variant))}
    for run in browsing:
        directory = folder / "browser" / run["id"]
        calls = [r for r in receipts if r.get("run_id") == run["id"]]
        assert len(calls) == len(run["steps"]) <= plan["browser"]["max_steps"]
        for call in calls:
            observation = json.loads(
                (directory / f"{call['step']:02d}-observation.json").read_text()
            )
            assert digest(observation) == call["observation_sha256"]
            assert (directory / f"{call['step']:02d}-before.png").exists()
        assert (directory / "final.png").exists()
        assert (directory / "final-observation.json").exists()
    report = {
        "audited_at": stamp(),
        "passed": True,
        "model_receipts": len(receipts),
        "finance_answers": len(finance),
        "identical_finance_input_pairs": len(finance) // 2,
        "browser_runs_with_saved_screenshots": len(browsing),
        "model_api_errors": sum(r["status"] != "ok" for r in receipts),
        "browser_action_errors": sum("action_error" in s for r in browsing for s in r["steps"]),
        "original_code_hashes_match": True,
        "input_and_observation_hashes_match": True,
    }
    save(folder / "audit.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
