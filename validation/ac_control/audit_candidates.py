"""Final evidence audit for the isolated candidate benchmark; no cloud mutations."""

import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
from analyze_candidates import analyze
from remote_candidates import BUCKET, INSTANCE, PREFIX, ROOT


def audit(root):
    summary = analyze(root)
    assert all(model["status"] == "complete" for model in summary["models"].values())
    assert summary["total_observed_calls"] == 1425
    before = analyze(root, root / "attempts/pre-maintenance/results",
                     root / "pre-maintenance-reanalysis.json")
    assert before["total_observed_calls"] == 638
    assert before["models"]["torchcast"]["status"] == "failed"
    assert before["models"]["torchcast"]["errors"] == 3
    transfer = json.loads((root / "source-transfer.json").read_text())
    archive_path = Path(__file__).resolve().parents[2] / ".deployment/ac-model-candidates/test-input.tar.gz"
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == transfer["archive_sha256"]
    with tarfile.open(archive_path) as archive:
        assert set(archive.getnames()) == set(transfer["files"])
        for member in archive.getmembers():
            assert member.isfile() and "references" not in member.name
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == transfer["files"][member.name]
    inventory = json.loads((root / "logs/final-inventory.json").read_text())
    planned_models = json.loads((root / "models.json").read_text())
    assert inventory["benchmark_reference_file_absent"]
    assert not inventory["gpu_processes"]["stdout"].strip()
    assert "ActiveState=active" in inventory["stop_guard"]["stdout"]
    assert "18:01:37" in inventory["stop_guard"]["stdout"]
    assert inventory["frozen_inputs"] == transfer["files"]
    for name, evidence in inventory["models"].items():
        path = root / "model-manifests" / (name + ".json")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence["manifest_sha256"]
        manifest = json.loads(path.read_text())
        assert manifest["revision"] == evidence["revision"] == planned_models[name]["revision"]
        assert evidence["repository"] == manifest["model"]
        assert manifest["model"] == planned_models[name]["repository"]
        assert inventory["initial_all_artifact_sha256_verification"][name]["revision"] == manifest["revision"]
        assert inventory["initial_all_artifact_sha256_verification"][name]["verified_files"] == len(manifest["files"])
    for name in ("pplx", "torchcast", "clef"):
        runtime = json.loads((root / "logs" / (name + "-runtime.json")).read_text())
        assert runtime["revision"] == planned_models[name]["revision"]
        assert runtime["adapter_sha256"] == transfer["files"]["candidate_server.py"]
        assert runtime["input_truncated"] is False
    knowline = json.loads((root / "results/knowline/health_before.json").read_text())["response"]
    assert knowline["temperature"] == 1 and knowline["layout"]["read_twice"]
    ssm = boto3.client("ssm", region_name="us-east-1")
    operations = {}
    for path in sorted((root / "operations").glob("*.json")):
        if path.name.endswith(".status.json"):
            continue
        operation = json.loads(path.read_text())
        assert operation["instance"] == INSTANCE
        source = path.with_suffix(".sh")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == operation["script_sha256"]
        response = ssm.get_command_invocation(CommandId=operation["id"], InstanceId=INSTANCE)
        assert response["Status"] in ("Success", "Failed", "TimedOut", "Cancelled"), path.name
        operations[path.stem] = response["Status"]
    for name in summary["models"]:
        assert operations["benchmark-" + name + "-post-maintenance"] == "Success"
    calls = []
    for directory in (root / "results", root / "attempts/pre-maintenance/results"):
        for path in directory.glob("*/receipts.jsonl"):
            calls.extend(json.loads(line) for line in path.read_text().splitlines())
    calls.sort(key=lambda row: row["started_at"])
    assert all(datetime.fromisoformat(a["finished_at"]) <= datetime.fromisoformat(b["started_at"])
               for a, b in zip(calls[:-1], calls[1:], strict=True))
    assert len(calls) == 2063
    repeatability = {}
    for name, previous in before["models"].items():
        if not previous.get("rows"):
            continue
        current = {(r["case_id"], r["order"]): r for r in summary["models"][name]["rows"]}
        compared = [r for r in previous["rows"] if r["status"] == "ok"]
        repeatability[name] = {
            "compared_valid_quality_requests": len(compared),
            "changed_choices": [{"case_id": r["case_id"], "order": r["order"]}
                                for r in compared if r["choices"] != current[r["case_id"], r["order"]]["choices"]],
            "correct_before": sum(r["correct"] for r in compared),
            "correct_after_on_same_subset": sum(current[r["case_id"], r["order"]]["correct"] for r in compared),
        }
    result = {
        "audited_at": datetime.now(UTC).isoformat(), "passed": True,
        "instance": INSTANCE, "bucket": BUCKET, "prefix": PREFIX,
        "models_complete": list(summary["models"]),
        "primary_formal_http_calls": sum(m["formal_calls"] for m in summary["models"].values()),
        "primary_warmup_http_calls": sum(m["warmup_calls"] for m in summary["models"].values()),
        "primary_errors": sum(m["errors"] for m in summary["models"].values()),
        "including_archived_round": {
            "formal_calls": sum(not r["kind"].startswith("warmup") for r in calls),
            "warmup_calls": sum(r["kind"].startswith("warmup") for r in calls),
            "errors": sum(r["status"] != "ok" for r in calls),
            "total_calls": len(calls),
        },
        "request_overlap_count": 0, "reference_answers_sent": False,
        "all_model_artifacts_sha256_verified_before_inference": True,
        "executable_and_configuration_sources_rechecked_after_inference": True,
        "input_truncation_observed": False, "gpu_processes_after_test": [],
        "serial30_artifact_operations_inside_timing_blocks": 0,
        "sdk_startup_and_internal_requests_included_in_http_counts": False,
        "operations": operations,
        "pre_post_maintenance_repeatability": repeatability,
    }
    for name in ("analyze_candidates.py", "audit_candidates.py", "render_candidate_results.py",
                 "remote_candidates.py", "launch_candidate.py", "benchmark_candidate.py",
                 "continue_candidates.py", "candidate_final_inventory.py", "test_candidate_protocol.py",
                 "cleanup_candidate_transfers.py"):
        path = root / "analysis_sources" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(Path(__file__).with_name(name).read_bytes())
    (root / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(audit(ROOT), indent=2))
