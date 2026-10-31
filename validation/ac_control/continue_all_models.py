"""Advance preparation and the seven GPU runs without overlapping model requests."""

import argparse
import json
import time

import boto3
from all_models_infra import ACTIVE_INSTANCE, collect, status, submit
from all_models_protocol import PROVIDERS, ROOT, save, stamp
from prepare_all_models_runtime import benchmark, bootstrap, launch
from recover_all_models_capacity import launch as recover_capacity


def note(**values):
    print(json.dumps({"at": stamp(), **values}), flush=True)


def wait_operation(name):
    while True:
        current = status(name)
        if current["Status"] == "Success":
            note(operation=name, status="Success")
            return
        if current["Status"] not in ("Pending", "InProgress", "Delayed"):
            raise RuntimeError(f"{name}: {current['Status']}; inspect retained operation logs")
        time.sleep(20)


def main(controller_name="gpu-controller"):
    assert "/" not in controller_name
    controller = ROOT / (controller_name + ".json")
    assert not controller.exists(), "Do not automatically replay a controller"
    state = {"started_at": stamp(), "status": "running", "phase": "capacity"}
    save(controller, state)
    try:
        while not ACTIVE_INSTANCE.exists():
            note(capacity=recover_capacity())
            if not ACTIVE_INSTANCE.exists():
                time.sleep(30)
        active = json.loads(ACTIVE_INSTANCE.read_text())
        instance = active["instance_id"]
        ssm = boto3.client("ssm", region_name=active.get("region", "us-east-1"))
        while True:
            rows = ssm.describe_instance_information(
                Filters=[{"Key": "InstanceIds", "Values": [instance]}])["InstanceInformationList"]
            if rows and rows[0]["PingStatus"] == "Online":
                break
            time.sleep(20)
        state.update(phase="bootstrap", instance_id=instance)
        save(controller, state)
        submit("replacement-inventory", "\n".join([
            "set -eu", "cloud-init status --wait",
            "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv",
            "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader",
            "df -h /", "systemctl show ac-nine-auto-stop.timer --property=ActiveState,NextElapseUSecMonotonic",
            "test -x /opt/ac-candidate-tests/tools/bin/uv",
        ]), 1200)
        wait_operation("replacement-inventory")
        note(bootstrap=bootstrap())
        wait_operation("prepare-complete-runtime")
        collect()
        state["phase"] = "wait_cloud"
        save(controller, state)
        while True:
            metas = [json.loads((ROOT / "results" / p / "run.json").read_text()) for p in ("jev", "gpt")]
            if any(m["status"] == "failed" for m in metas):
                raise RuntimeError("Cloud run failed; GPU inference has not started")
            if all(m["status"] in ("complete", "complete_with_errors") and m["calls"] == 2049 for m in metas):
                break
            time.sleep(20)
        for provider in PROVIDERS[2:]:
            state.update(phase="launch", provider=provider)
            save(controller, state)
            note(launch=launch(provider))
            wait_operation("start-" + provider + "-nine-models")
            state["phase"] = "benchmark"
            save(controller, state)
            note(benchmark=benchmark(provider))
            wait_operation("benchmark-" + provider + "-nine-models")
            collect()
            meta = json.loads((ROOT / "results" / provider / "run.json").read_text())
            assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049, provider
            note(provider=provider, calls=meta["calls"], errors=meta["errors"], status=meta["status"])
        state.update(status="complete", phase="finished")
    except BaseException as error:
        state.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        state["updated_at"] = stamp()
        save(controller, state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-name", default="gpu-controller")
    main(parser.parse_args().controller_name)
