"""Finish the predeclared runtime screen after causal candidates fail their gate."""

import json
import subprocess
import sys
import time
from pathlib import Path

import boto3
from analyze_h2o_official import analyze
from plan_h2o_official_jobs import build
from run_resident import save, stamp


def main(root):
    assert not json.loads((root / "selection.json").read_text())["development_eligible"]
    assert (root / "early_stop_amendment.json").exists()
    client = boto3.client("ssm", region_name="us-east-1")
    remote = Path(__file__).with_name("remote_h2o_official.py")

    def wait(name=None):
        transfer = json.loads((root / "transfer.json").read_text())
        command = (next(c for c in transfer["commands"] if c["name"] == name)
                   if name else transfer["commands"][-1])
        while True:
            try:
                invocation = client.get_command_invocation(
                    CommandId=command["id"], InstanceId=transfer["instance"])
            except client.exceptions.InvocationDoesNotExist:
                time.sleep(2)
                continue
            if invocation["Status"] in ("Success", "Failed", "TimedOut", "Cancelled"):
                subprocess.run([sys.executable, str(remote), "collect", "--run", str(root)], check=True)
                return invocation["Status"]
            time.sleep(20)

    def operation(action, name):
        transfer = json.loads((root / "transfer.json").read_text())
        if name not in [c["name"] for c in transfer["commands"]]:
            subprocess.run([sys.executable, str(remote), action, "--run", str(root), "--name", name], check=True)
        return wait(name)

    def job(name, kind):
        if not (root / "jobs" / (name + ".json")).exists():
            build(root, name, kind)
        assert operation("job", name) == "Success", name
        analyze(root)

    assert wait("restart-original") == "Success", "Original restart failed"
    job("restart_stability", "restart_stability")
    job("eager_baseline", "baseline_latency")
    status = operation("gdn1024", "gdn-start")
    result = {"recorded_at": stamp(), "startup_status": status, "profile": "baseline",
              "attention": "bidirectional", "heldback_queried": False}
    if status == "Success":
        job("gdn_baseline_screen", "baseline_screen")
        stages = analyze(root)["stages"]
        key = "baseline:bidirectional:full30"
        old = stages["eager_baseline"]["latency"][key]["client_ms"]["mean"]
        new = stages["gdn_baseline_screen"]["latency"][key]["client_ms"]["mean"]
        result.update(eager_full30_ms=old, gdn_full30_ms=new, speedup=old / new,
                      screen_passed=new <= old * .9)
        save(root / "baseline_runtime_screen.json", result)
        if result["screen_passed"]:
            print("Screen passed; full validation is required before any adoption.", flush=True)
            return
        assert operation("rollback", "restore-original") == "Success"
    else:
        result.update(screen_passed=False, reason="GDN startup failed; controller rolls back")
        save(root / "baseline_runtime_screen.json", result)
    job("final_stability", "restart_stability")
    print("Rejected runtime screen; original service restored and checked.", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
