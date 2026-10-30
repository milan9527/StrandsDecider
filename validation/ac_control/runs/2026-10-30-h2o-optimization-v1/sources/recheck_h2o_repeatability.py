"""Record a bounded follow-up after a same-configuration restart changed N09."""

import argparse
import json
from pathlib import Path

from run_ablation import call, choices
from run_resident import save, sha, snapshot, stamp, wire


def run(root):
    output = root / "repeatability"
    output.mkdir(exist_ok=True)
    if (output / "receipts.jsonl").exists():
        raise FileExistsError("Repeatability observations already exist")
    cases = {row["case_id"]: row["payload"] for row in json.loads((root / "cases.json").read_text())
             if row["order"] == "original"}
    schedule = []
    for repetition in range(3):
        schedule.extend({"case_id": key, "mode": "full_30", "repetition": repetition}
                        for key in ("N03", "N09", "N10"))
        schedule.append({"case_id": "N09", "mode": "single_key", "repetition": repetition})
    save(output / "plan.json", {
        "prepared_at": stamp(), "reason": "Restored original runtime changed N09; investigate repeatability",
        "schedule": schedule, "external_concurrency": 1, "automatic_retries": 0,
        "changes": "No prompt/candidate edits; separate single-key N09 uses full state and original t_swing_angle question",
        "scoring": "Supplemental diagnosis only; never replace prior 50-case results",
    })
    snapshot(output, "before")
    rows = []
    with (output / "receipts.jsonl").open("x") as stream:
        for task in schedule:
            payload = cases[task["case_id"]]
            if task["mode"] == "single_key":
                payload = {"state": payload["state"],
                           "questions": {"t_swing_angle": payload["questions"]["t_swing_angle"]}}
            row = {**task, "started_at": stamp(), "request": payload, "input_sha256": sha(payload),
                   **call("http://127.0.0.1:18803/v1/systemone", payload, {}), "finished_at": stamp()}
            if row["status"] == "ok":
                row["choices"] = choices(row["response"], payload, "h2oai/h2o-lightning-4b")
            stream.write(wire(row) + "\n")
            stream.flush()
            rows.append(row)
            assert row["status"] == "ok", "Failed observation retained; no retry"
    snapshot(output, "after")
    save(output / "run.json", {"status": "complete", "finished_at": stamp(), "actual_calls": len(rows)})
    print(wire({"status": "complete", "calls": len(rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    run(parser.parse_args().run)
