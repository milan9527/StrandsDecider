"""Audit the finished five-model run, stop its EC2, and clean verified transfers."""

import hashlib
import json
import shlex
import time
from datetime import UTC, datetime
from pathlib import Path

import boto3
from audit_candidates import audit
from cleanup_candidate_transfers import cleanup
from continue_candidates import wait
from remote_candidates import BUCKET, INSTANCE, PREFIX, REMOTE, ROOT, save, submit
from render_candidate_results import render


def finalize():
    # No inference is launched here. The separate driver must finish every model first.
    assert all(json.loads((ROOT / "results" / name / "run.json").read_text())["status"] == "complete"
               for name in ("pplx", "knowline", "torchcast", "clef", "h2o"))
    source = Path(__file__).with_name("candidate_final_inventory.py").read_bytes()
    key = "input/" + PREFIX + "/final-inventory.py"
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=key, Body=source)
    digest = hashlib.sha256(source).hexdigest()
    target = REMOTE + "/final-inventory.py"
    script = "\n".join([
        "set -eu",
        "aws s3 cp s3://" + BUCKET + "/" + key + " " + target + " --only-show-errors",
        REMOTE + "/tools/bin/python -c " + shlex.quote(
            "import hashlib,pathlib; assert hashlib.sha256(pathlib.Path("
            + repr(target) + ").read_bytes()).hexdigest() == " + repr(digest)),
        REMOTE + "/tools/bin/python " + target,
        "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX
        + "/logs --only-show-errors",
    ])
    if not (ROOT / "operations/final-inventory.json").exists():
        submit("final-inventory", script, 300)
    wait("final-inventory")
    render(ROOT)
    result = audit(ROOT)
    print(json.dumps(result, indent=2), flush=True)
    destination = ROOT / "analysis_sources/finalize_candidates.py"
    destination.write_bytes(Path(__file__).read_bytes())
    ec2 = boto3.client("ec2", region_name="us-east-1")
    record = ROOT / "infrastructure/stopped.json"
    if not record.exists():
        request_record = ROOT / "infrastructure/stop-request.json"
        if not request_record.exists():
            response = ec2.stop_instances(InstanceIds=[INSTANCE])
            save(request_record, {
                "requested_at": datetime.now(UTC).isoformat(), "response": response,
            })
        deadline = time.monotonic() + 600
        while True:
            instance = ec2.describe_instances(InstanceIds=[INSTANCE])["Reservations"][0]["Instances"][0]
            print("EC2", instance["State"]["Name"], flush=True)
            if instance["State"]["Name"] == "stopped":
                break
            # EC2 describe can briefly return the prior state after stop_instances succeeds.
            assert instance["State"]["Name"] in ("running", "stopping"), instance["State"]
            assert time.monotonic() < deadline, "EC2 did not stop within ten minutes"
            time.sleep(15)
        volumes = ec2.describe_volumes(VolumeIds=[
            mapping["Ebs"]["VolumeId"] for mapping in instance["BlockDeviceMappings"]
        ])["Volumes"]
        save(record, {"verified_at": datetime.now(UTC).isoformat(), "instance": instance,
                      "volumes_retained": volumes})
    if not (ROOT / "transfer_cleanup.json").exists():
        print(json.dumps(cleanup(), indent=2), flush=True)


if __name__ == "__main__":
    finalize()
