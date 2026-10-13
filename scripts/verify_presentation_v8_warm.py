"""Correlate saved Jev browser windows with Lambda logs; do not call models."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/presentations/v8"
LOG_GROUP = "/aws/lambda/strands-decider-demo-jev"


def milliseconds(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000


def main():
    observed = json.loads((OUT / "live-observations.json").read_text())
    warm = next(w for w in observed["warmups"] if w["request"]["provider"] == "jev")
    windows = [("warmup", "intake", warm)]
    for case, data in observed["cases"].items():
        for turn in data["dialogues"]:
            side = turn["sides"]["jev"]
            windows.append((case, side["request"]["stage"], side))

    client = boto3.client("logs", region_name="us-east-1")
    events = []
    for page in client.get_paginator("filter_log_events").paginate(
        logGroupName=LOG_GROUP,
        startTime=int(milliseconds(observed["captured_at"])) - 1000,
        endTime=int(milliseconds(observed["measured_finished_at"])) + 5000,
    ):
        events.extend(page["events"])

    starts, reports = {}, {}
    for event in events:
        message = event["message"]
        request_id = re.search(r"^(?:START|REPORT) RequestId: ([\w-]+)", message)
        if request_id:
            (starts if message.startswith("START") else reports)[request_id[1]] = event

    entries = []
    for case, stage, side in windows:
        lower = milliseconds(side["startedAt"])
        upper = lower + side["elapsedMs"]
        matched = [
            (rid, event) for rid, event in starts.items() if lower <= event["timestamp"] <= upper
        ]
        assert len(matched) == 1, (case, stage, "not exactly one Lambda START in browser window")
        rid, event = matched[0]
        assert rid in reports, (case, stage, "REPORT not yet available")
        report = reports[rid]
        message = report["message"]
        duration = re.search(r"\tDuration: ([\d.]+) ms", message)
        initialization = re.search(r"\tInit Duration: ([\d.]+) ms", message)
        entries.append(
            {
                "case": case,
                "stage": stage,
                "browser_started_at": side["startedAt"],
                "browser_elapsed_ms": side["elapsedMs"],
                "backend_total_ms": side["result"]["timings"]["backend_total_ms"],
                "request_id": rid,
                "log_stream": event["logStreamName"],
                "lambda_started_at": datetime.fromtimestamp(
                    event["timestamp"] / 1000, UTC
                ).isoformat(),
                "lambda_duration_ms": float(duration[1]),
                "lambda_init_ms": float(initialization[1]) if initialization else None,
                "lambda_report": message.strip(),
            }
        )
    assert len(entries) == 21
    assert len({e["request_id"] for e in entries}) == 21
    warm_stream = entries[0]["log_stream"]
    measured = entries[1:]
    verified = all(e["lambda_init_ms"] is None and e["log_stream"] == warm_stream for e in measured)
    result = {
        "verified_at": datetime.now(UTC).isoformat(),
        "region": "us-east-1",
        "log_group": LOG_GROUP,
        "association_method": "Exactly one Lambda START timestamp inside each Jev browser request window; REPORT matched by RequestId. Application does not expose Lambda IDs.",
        "limitations": "Confirms reuse of our Lambda proxy environment only; upstream Jev infrastructure state and pure inference time are not observable.",
        "measured_calls": len(measured),
        "measured_calls_with_init_duration": sum(e["lambda_init_ms"] is not None for e in measured),
        "verified_all_measured_warm": verified,
        "warmup": entries[0],
        "measured": measured,
    }
    (OUT / "lambda-warm-verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    assert verified, "Do not publish a warmed result if any measured Lambda invocation initialized."
    print(
        "Verified 20/20 measured Jev calls reused the prewarmed Lambda environment, with no Init Duration."
    )


if __name__ == "__main__":
    main()
