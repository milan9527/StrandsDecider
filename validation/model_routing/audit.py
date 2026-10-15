"""Recompute results and verify paired inputs, plans, metadata and source hashes."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from prepare import payload, sha
from run import grade, summarize

HERE = Path(__file__).resolve().parent


def main():
    reports = []
    for name in ("2026-10-13-live", "2026-10-13-natural"):
        folder = HERE / "runs" / name
        plan = json.loads((folder / "plan.json").read_text())
        metadata = json.loads((folder / "run.json").read_text())
        rows = json.loads((folder / "results.json").read_text())
        receipts = [
            json.loads(line) for line in (folder / "receipts.jsonl").read_text().splitlines()
        ]
        assert metadata["status"] == "complete"
        assert len(receipts) == len(rows) == metadata["actual_calls"] == plan["max_calls"]
        assert metadata["downstream_calls"] == 0
        assert sha({k: v for k, v in plan.items() if k != "plan_sha256"}) == plan["plan_sha256"]
        for source in plan["sources"]:
            assert (
                sha256((HERE / "sources" / source["file"]).read_bytes()).hexdigest()
                == source["sha256"]
            )
        for path, checksum in metadata["source_code_sha256"].items():
            assert sha256((HERE.parent / path).read_bytes()).hexdigest() == checksum
        cases = {case["id"]: case for case in plan["cases"]}
        recomputed = []
        for receipt in receipts:
            case = cases[receipt["case_id"]]
            request = payload(case, receipt["variant"])
            assert receipt["input"] == request
            assert receipt["input_sha256"] == sha(request)
            assert receipt["attempt"] == 1 and not receipt["retry"]
            assert receipt["status"] == "ok"
            recomputed.append(grade(case, receipt, receipt["variant"]))
        assert rows == recomputed
        assert summarize(rows, receipts) == json.loads((folder / "summary.json").read_text())
        for case in cases.values():
            for variant in plan["variants"]:
                pair = [
                    r for r in receipts if r["case_id"] == case["id"] and r["variant"] == variant
                ]
                assert len(pair) == 2 and {r["provider"] for r in pair} == {"jev", "decider"}
                assert len({r["input_sha256"] for r in pair}) == 1
        reports.append(
            {
                "run": name,
                "passed": True,
                "calls": len(receipts),
                "identical_input_pairs": len(receipts) // 2,
                "max_reported_decider_input_tokens": max(
                    r["response"]["usage"]["input_tokens"]
                    for r in receipts
                    if r["provider"] == "decider"
                ),
            }
        )
    output = {
        "audited_at": datetime.now(UTC).isoformat(),
        "runs": reports,
        "total_calls": sum(r["calls"] for r in reports),
        "downstream_calls": 0,
        "new_model_calls_for_audit": 0,
    }
    (HERE / "verification.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
