"""Run local models sequentially after the hosted comparisons have finished."""

import argparse
import fcntl
import json
import shlex
import time

import boto3

from all_models_protocol import save, stamp
from optimized_all_models_infra import (
    BUCKET, CONFIG, PREFIX, REMOTE, ROOT, active, collect, status, submit,
)
from optimized_all_models_protocol import profile_order


def wait_operation(name):
    while True:
        result = status(name)
        if result["Status"] in ("Success", "Failed", "Cancelled", "TimedOut", "Cancelling"):
            if result["Status"] != "Success":
                raise RuntimeError(f"{name}: {result['Status']}; see preserved operation output")
            return result
        time.sleep(20)


def launch(provider):
    import prepare_all_models_runtime as runtime

    runtime.ROOT = ROOT
    runtime.REMOTE = REMOTE
    runtime.PREFIX = PREFIX
    runtime.submit = submit
    result = runtime.launch(provider, attempt="input-optimization")
    return result


def benchmark(provider):
    unit = ("ac-nine-" if provider in ("decider", "liquid") else "ac-candidate-") + provider
    endpoint = "http://127.0.0.1:" + ("18801" if provider == "liquid" else "18811")
    cleanup = "\n".join([
        "benchmark_exit=$?",
        "systemctl stop " + unit,
        *(['docker stop ' + unit + ' >/dev/null 2>&1 || true'] if provider in ("decider", "liquid") else []),
        "journalctl -u " + unit + " --no-pager -o short-iso > "
        + REMOTE + "/logs/" + provider + "-complete.log",
        "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX + "/logs --only-show-errors",
        'exit "$benchmark_exit"',
    ])
    script = ["set -eu", "trap " + shlex.quote(cleanup) + " EXIT",
              "systemctl is-active --quiet " + unit]
    for profile in profile_order(provider):
        folder = REMOTE + "/run/profiles/" + profile
        script.extend([
            shlex.join([REMOTE + "/runner-env/bin/python", "-u", REMOTE + "/run/run_optimized_models.py",
                        "--run", folder, "--provider", provider, "--endpoint", endpoint])
            + " > " + REMOTE + "/logs/" + provider + "-" + profile + "-runner.log 2>&1",
            # Archive work is between profiles; it is outside every request/serial timer.
            "aws s3 sync " + folder + "/results/" + provider + " s3://" + BUCKET + "/output/"
            + PREFIX + "/profiles/" + profile + "/results/" + provider + " --only-show-errors",
        ])
    return submit("benchmark-" + provider + "-input-optimization", "\n".join(script), 21600)


def main(resume=False):
    path = ROOT / "gpu-orchestration.json"
    if path.exists():
        assert resume, "Existing controller state requires --resume"
        prior = json.loads(path.read_text())
        assert prior["status"] != "complete", "GPU tests are already complete"
        archive = ROOT / "attempts/orchestration" / ("gpu-" + stamp().replace(":", "-") + ".json")
        save(archive, prior)
        controller = {
            "started_at": prior["started_at"], "resumed_at": stamp(),
            "status": "waiting_for_cloud", "completed": prior.get("completed", []),
            "prior_state": str(archive.relative_to(ROOT)),
        }
    else:
        controller = {"started_at": stamp(), "status": "waiting_for_cloud", "completed": []}
    save(path, controller)
    try:
        while True:
            cloud = json.loads((ROOT / "cloud-orchestration.json").read_text())
            if cloud["status"] == "failed":
                raise RuntimeError("Hosted tests did not finish; retain global concurrency=1")
            cloud_runs = [ROOT / "profiles" / profile / "results" / provider / "run.json"
                          for profile in ("baseline", "compact_catalog", "schema_once")
                          for provider in ("jev", "gpt")]
            cloud_complete = all(
                file.exists() and json.loads(file.read_text()).get("status") in ("complete", "complete_with_errors")
                and json.loads(file.read_text()).get("calls") == 2049 for file in cloud_runs
            )
            if cloud["status"] == "complete" and cloud_complete:
                break
            time.sleep(20)
        wait_operation("prepare-us-east-runtimes")
        wait_operation("apply-full-context-input-amendment")
        controller["status"] = "running"
        for provider in ("decider", "liquid", "pplx", "knowline", "torchcast", "clef", "h2o"):
            if provider in controller["completed"]:
                for profile in profile_order(provider):
                    meta = json.loads((ROOT / "profiles" / profile / "results" / provider / "run.json").read_text())
                    assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049
                continue
            controller["active"] = {"provider": provider, "phase": "startup", "started_at": stamp()}
            save(path, controller)
            print(json.dumps(controller["active"]), flush=True)
            if not (ROOT / "operations" / ("start-" + provider + "-input-optimization.json")).exists():
                launch(provider)
            wait_operation("start-" + provider + "-input-optimization")
            controller["active"]["phase"] = "benchmark"
            save(path, controller)
            if not (ROOT / "operations" / ("benchmark-" + provider + "-input-optimization.json")).exists():
                benchmark(provider)
            wait_operation("benchmark-" + provider + "-input-optimization")
            collect()
            for profile in profile_order(provider):
                meta = json.loads((ROOT / "profiles" / profile / "results" / provider / "run.json").read_text())
                assert meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049
            controller["completed"].append(provider)
            save(path, controller)
            print(json.dumps({"completed": provider, "recorded_at": stamp()}), flush=True)
        controller["status"] = "complete"
        controller["active"] = None
    except BaseException as error:
        controller.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        controller["finished_at"] = stamp()
        save(path, controller)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    with (ROOT / "gpu-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main(args.resume)
