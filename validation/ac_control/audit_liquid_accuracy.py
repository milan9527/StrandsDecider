"""Finalize the frozen Liquid trial; optionally verify and remove its S3 transfers."""

import argparse
import contextlib
import hashlib
import io
import json
import tarfile
from datetime import datetime
from pathlib import Path

import boto3
from analyze_liquid_accuracy import analyze
from run_resident import save, sha, stamp


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(root, cleanup=False):
    with contextlib.redirect_stdout(io.StringIO()):
        result = analyze(root)
    plan = json.loads((root / "plan.json").read_text())
    capabilities = json.loads((root / "command_set.json").read_text())
    assert len(capabilities["commandSet"]) == 30 and sha(capabilities) == plan["capabilities_sha256"]
    for phase in ("development", "validation"):
        cases = json.loads((root / (phase + "_cases.json")).read_text())
        for case in cases:
            assert json.loads(case["payload"]["state"])["commandSet"] == capabilities["commandSet"]
    selection = json.loads((root / "selection.json").read_text())
    transfer = json.loads((root / "transfer.json").read_text())
    phases = result["phases"]
    assert set(phases) == {"development", "validation"}
    assert all(phase["status"] == "complete" for phase in phases.values())
    assert phases["development"]["observations"] == plan["development_observations"]
    candidate = selection["candidate"]
    validation_strategies = list(dict.fromkeys(["baseline", "two_stage", candidate]))
    assert phases["validation"]["observations"] == plan["validation_cases"] * 2 * len(validation_strategies)
    assert selection["development_receipts_sha256"] == phases["development"]["receipts_sha256"]
    assert selection["validation_outputs_seen"] is False
    development_meta = json.loads((root / "development/run.json").read_text())
    validation_meta = json.loads((root / "validation/run.json").read_text())
    assert (datetime.fromisoformat(plan["prepared_at"])
            < datetime.fromisoformat(development_meta["started_at"])
            < datetime.fromisoformat(development_meta["finished_at"])
            < datetime.fromisoformat(selection["selected_at"])
            < datetime.fromisoformat(validation_meta["started_at"]))
    assert validation_meta["strategies"] == validation_strategies
    scores = phases["development"]["scores"]
    control = scores["two_stage"]
    eligible = [
        strategy for strategy, score in scores.items()
        if strategy not in ("baseline", "two_stage")
        and score["original_total"]["correct"] > control["original_total"]["correct"]
        and all(score[group]["correct"] >= control[group]["correct"]
                for group in ("spec_original", "extension_original", "reversed_total"))
    ]

    def rank(strategy):
        score = scores[strategy]
        original = score["original_total"]
        return (original["correct"], score["reversed_total"]["correct"],
                -original["missing_pairs"], -original["extra_pairs"], -original["client_ms"]["mean"])

    assert eligible == selection["eligible"]
    assert candidate == (max(eligible, key=rank) if eligible else "two_stage")
    validation = phases["validation"]["scores"]
    accepted = (
        validation[candidate]["original_total"]["correct"]
        > validation["two_stage"]["original_total"]["correct"]
        and validation[candidate]["reversed_total"]["correct"]
        >= validation["two_stage"]["reversed_total"]["correct"]
    )
    recommendation = {
        "candidate": candidate,
        "recommended_strategy": candidate if accepted else "two_stage",
        "validation_passed_frozen_rule": accepted,
        "scope": "Opt-in AC client protocol; native model service and generic application are unchanged.",
        "selection_sha256": digest((root / "selection.json").read_bytes()),
        "receipts_sha256": {phase: data["receipts_sha256"] for phase, data in phases.items()},
        "validation_original": {
            strategy: validation[strategy]["original_total"]["correct"]
            for strategy in ("two_stage", candidate)
        },
        "validation_reversed": {
            strategy: validation[strategy]["reversed_total"]["correct"]
            for strategy in ("two_stage", candidate)
        },
    }
    target = root / "recommendation.json"
    if target.exists():
        assert json.loads(target.read_text()) == recommendation
    else:
        save(target, recommendation)
    archives = {}
    for command in transfer["commands"]:
        phase = command["phase"]
        data = (root / (phase + "_input.tar.gz")).read_bytes()
        assert digest(data) == command["archive_sha256"]
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            names = archive.getnames()
            assert names == command["files"]
            assert "references.json" not in names
            for member in archive.getmembers():
                assert member.isfile()
                expected = root / "sources" / member.name if member.name in plan["source_sha256"] else root / member.name
                assert archive.extractfile(member).read() == expected.read_bytes()
        archives[phase] = {"sha256": digest(data), "members": names, "reference_file_absent": True}
    summary = {
        "audited_at": stamp(), "passed": True,
        "observations": sum(phase["observations"] for phase in phases.values()),
        "formal_calls": sum(phase["actual_calls"] for phase in phases.values()),
        "warmup_calls": sum(phase["warmup_calls"] for phase in phases.values()),
        "formal_errors": sum(row["status"] != "ok" for phase in phases.values() for row in phase["rows"]),
        "request_overlap_count": result["request_overlap_count"],
        "services_unchanged": result["services_unchanged"],
        "selection_precedes_validation": True, "archives": archives,
        "recommendation": recommendation,
        "source_sha256": {
            name: digest(Path(__file__).with_name(name).read_bytes())
            for name in ("audit_liquid_accuracy.py", "analyze_liquid_accuracy.py",
                         "remote_liquid_accuracy.py", "prepare_liquid_accuracy.py",
                         "test_liquid_accuracy.py")
        },
    }
    for name in summary["source_sha256"]:
        saved = root / "analysis_sources" / name
        saved.parent.mkdir(exist_ok=True)
        saved.write_bytes(Path(__file__).with_name(name).read_bytes())
    save(root / "audit.json", summary)
    if cleanup:
        cleanup_transfers(root, transfer)
    print(json.dumps({key: summary[key] for key in (
        "passed", "observations", "formal_calls", "warmup_calls", "formal_errors",
        "request_overlap_count", "services_unchanged", "recommendation")}, indent=2))


def cleanup_transfers(root, transfer):
    receipt = root / "transfer_cleanup.json"
    assert not receipt.exists(), "Cleanup already completed"
    ssm = boto3.client("ssm", region_name=transfer["region"])
    for command in transfer["commands"]:
        invocation = ssm.get_command_invocation(
            CommandId=command["id"], InstanceId=transfer["instance"])
        assert invocation["Status"] == "Success"
    s3 = boto3.client("s3", region_name=transfer["region"])
    bucket = transfer["bucket"]
    assert s3.get_bucket_versioning(Bucket=bucket).get("Status") is None
    verified = []
    prefixes = ("input/" + transfer["prefix"] + "/", "output/" + transfer["prefix"] + "/results/")
    inputs = {command["input_key"]: root / (command["phase"] + "_input.tar.gz")
              for command in transfer["commands"]}
    for prefix in prefixes:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if prefix == prefixes[0]:
                    assert key in inputs
                    local = inputs[key]
                else:
                    relative = Path(key.removeprefix(prefix))
                    assert not relative.is_absolute() and ".." not in relative.parts
                    local = root / relative
                data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                assert data == local.read_bytes(), f"Remote evidence differs: {key}"
                verified.append({"key": key, "bytes": len(data), "sha256": digest(data)})
    assert verified and set(inputs) <= {item["key"] for item in verified}
    save(root / "transfer_verification.json", {
        "verified_at": stamp(), "bucket": bucket, "prefixes": prefixes, "objects": verified,
    })
    for item in verified:
        s3.delete_object(Bucket=bucket, Key=item["key"])
    for prefix in prefixes:
        assert s3.list_objects_v2(Bucket=bucket, Prefix=prefix)["KeyCount"] == 0
    save(receipt, {"finished_at": stamp(), "deleted_objects": len(verified),
                   "local_and_gpu_evidence_retained": True, "prefixes_empty": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    audit(args.run, args.cleanup)
