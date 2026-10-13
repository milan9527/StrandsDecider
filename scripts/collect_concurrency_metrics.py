"""Collect read-only Lambda initialization and ECS utilization evidence for a saved run."""

import argparse
import json
import re
from datetime import UTC, datetime, timedelta

import boto3


def deployment_snapshot(folder):
    """Preserve an existing start snapshot; otherwise capture current read-only configuration."""
    path = folder / "deployment-snapshot.json"
    if path.exists():
        return
    ecs = boto3.client("ecs", region_name="us-east-1")
    service = ecs.describe_services(
        cluster="strands-decider-demo", services=["strands-decider-demo"]
    )["services"][0]
    task = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    instances = boto3.client("ec2", region_name="us-east-1").describe_instances(
        Filters=[
            {"Name": "tag:DeciderGpuStack", "Values": ["strands-decider-demo-gpu"]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    snapshot = {
        "captured_at": datetime.now(UTC).isoformat(),
        "region": "us-east-1",
        "capture_phase": "after_measurement",
        "api": {
            "service": service["serviceName"],
            "desired_count": service["desiredCount"],
            "running_count": service["runningCount"],
            "task_definition_revision": task["revision"],
            "cpu_units": task["cpu"],
            "memory_mib": task["memory"],
            "architecture": task.get("runtimePlatform"),
            "containers": [
                {"name": c["name"], "image": c["image"].split("/")[-1], "command": c.get("command")}
                for c in task["containerDefinitions"]
            ],
        },
        "gpu_instances": [
            {
                "instance_type": instance["InstanceType"],
                "availability_zone": instance["Placement"]["AvailabilityZone"],
                "state": instance["State"]["Name"],
                "lifecycle": instance.get("InstanceLifecycle", "on-demand"),
            }
            for reservation in instances["Reservations"]
            for instance in reservation["Instances"]
        ],
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["status"] == "complete", "Wait for the benchmark to finish."
    deployment_snapshot(folder)
    start, end = dt(manifest["started_at"]), dt(manifest["finished_at"])
    logs = boto3.client("logs", region_name="us-east-1")
    events = []
    for page in logs.get_paginator("filter_log_events").paginate(
        logGroupName="/aws/lambda/strands-decider-demo-jev",
        startTime=int(start.timestamp() * 1000),
        endTime=int(end.timestamp() * 1000) + 1000,
    ):
        events.extend(page["events"])
    starts, reports = {}, {}
    for event in events:
        match = re.search(r"^(START|REPORT) RequestId: ([\w-]+)", event["message"])
        if match:
            (starts if match[1] == "START" else reports)[match[2]] = event
    invocations = []
    for request_id, start_event in starts.items():
        report = reports.get(request_id)
        if not report:
            continue
        duration = re.search(r"\tDuration: ([\d.]+) ms", report["message"])
        init = re.search(r"\tInit Duration: ([\d.]+) ms", report["message"])
        invocations.append(
            {
                "request_id": request_id,
                "started_at": datetime.fromtimestamp(
                    start_event["timestamp"] / 1000, UTC
                ).isoformat(),
                "start_timestamp_ms": start_event["timestamp"],
                "log_stream": start_event["logStreamName"],
                "duration_ms": float(duration[1]),
                "init_duration_ms": float(init[1]) if init else None,
            }
        )
    cells = []
    for cell in manifest["cells"]:
        if cell["provider"] != "jev":
            continue
        lower = dt(cell["started_at"]).timestamp() * 1000
        upper = dt(cell["finished_at"]).timestamp() * 1000
        measured = [r for r in invocations if lower <= r["start_timestamp_ms"] <= upper]
        cold = [r for r in measured if r["init_duration_ms"] is not None]
        cells.append(
            {
                "concurrency": cell["concurrency"],
                "expected_http_attempts": cell["attempts"],
                "lambda_starts_with_report": len(measured),
                "count_matches": len(measured) == cell["attempts"],
                "invocations_with_initialization": len(cold),
                "init_duration_ms": [r["init_duration_ms"] for r in cold],
                "execution_environments": len({r["log_stream"] for r in measured}),
                "request_ids": [r["request_id"] for r in measured],
            }
        )
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")
    metrics = {}
    for name in ("CPUUtilization", "MemoryUtilization"):
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/ECS",
            MetricName=name,
            Dimensions=[
                {"Name": "ClusterName", "Value": "strands-decider-demo"},
                {"Name": "ServiceName", "Value": "strands-decider-demo"},
            ],
            StartTime=start - timedelta(seconds=60),
            EndTime=end + timedelta(seconds=60),
            Period=60,
            Statistics=["Average", "Maximum"],
        )
        metrics[name] = [
            {**point, "Timestamp": point["Timestamp"].isoformat()}
            for point in sorted(response["Datapoints"], key=lambda p: p["Timestamp"])
        ]
    result = {
        "collected_at": datetime.now(UTC).isoformat(),
        "region": "us-east-1",
        "lambda_association": "Group by Lambda START timestamp inside each serially tested Jev measurement cell. Concurrent calls cannot be uniquely matched to individual HTTP requests because the API does not return Lambda request IDs.",
        "lambda_limitations": "Counts are checked against HTTP attempts; concurrent unrelated traffic could confound association. This observes our proxy, not upstream Jev inference or cold starts.",
        "jev_measured_cells": cells,
        "all_lambda_invocations_including_warmups": invocations,
        "ecs_utilization_percent": metrics,
        "ecs_latest_sample_bucket": {
            name: points[-1]["Timestamp"] if points else None for name, points in metrics.items()
        },
        "measurement_final_minute_bucket": end.replace(second=0, microsecond=0).isoformat(),
        "ecs_limitations": "60-second service metrics may combine adjacent providers, warmups and unrelated traffic; they do not measure GPU utilization and cannot establish individual request causality.",
    }
    (folder / "infrastructure-metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "jev_cells": [{k: v for k, v in c.items() if k != "request_ids"} for c in cells],
                "ecs_points": {k: len(v) for k, v in metrics.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    main(parser.parse_args().folder)
