"""Continue the frozen run through evaluation and offline reporting."""
import json
import subprocess
import sys
import time

from infra import BUCKET, HERE, MODEL, PREFIX, PYTHON, REMOTE, ROOT, collect, save, status, submit, transfer


def await_operation(name, phase):
    poll = 0
    while True:
        current = status(name)
        if current["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
            print(json.dumps({"operation": name, "status": current["Status"]}), flush=True)
            collect()
            if current["Status"] != "Success":
                raise RuntimeError(f"{name}: {current}")
            return
        poll += 1
        inspection = f"{phase}-controller-progress-{poll:04d}"
        folder = "training" if phase == "training" else "evaluation"
        log = "train.log" if phase == "training" else "evaluate.log"
        script = (
            f"test ! -f {REMOTE}/{folder}/progress.json || cat {REMOTE}/{folder}/progress.json\n"
            f"tail -2 {REMOTE}/{log}\n"
            f"test ! -f {REMOTE}/{folder}/checkpoints.json || cat {REMOTE}/{folder}/checkpoints.json\n"
        )
        submit(inspection, script, 60)
        time.sleep(2)
        observed = status(inspection)
        print(json.dumps({"operation": name, "status": current["Status"],
                          "progress": observed["StandardOutputContent"]}), flush=True)
        # Infrastructure polling never overlaps a second inference request.
        time.sleep(45)


def main():
    await_operation("lora-training-v1", "training")
    selection = json.loads((ROOT / "training/selection.json").read_text())
    assert not selection["heldout_used"] and selection["frozen_weights_unchanged"]
    files = {name: ROOT/name for name in ("test-inputs.json", "historical-cases.json")}
    files.update({name: HERE/name for name in ("evaluate.py",)})
    artifact = transfer("evaluation-input-v1", files)
    script = f'''set -eu
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
aws s3 cp s3://{BUCKET}/{artifact['key']} /tmp/liquid-lora-evaluation.tar.gz --only-show-errors
test "$(sha256sum /tmp/liquid-lora-evaluation.tar.gz | cut -d ' ' -f1)" = {artifact['sha256']}
tar -xzf /tmp/liquid-lora-evaluation.tar.gz -C {REMOTE}
mkdir -p {REMOTE}/evaluation
trap 'aws s3 sync {REMOTE}/evaluation s3://{BUCKET}/output/{PREFIX}/evaluation --only-show-errors; test ! -f {REMOTE}/evaluate.log || aws s3 cp {REMOTE}/evaluate.log s3://{BUCKET}/output/{PREFIX}/evaluate.log --only-show-errors' EXIT
systemd-run --unit ac-liquid-lora-eval --property=Restart=no --property=KillMode=control-group --property=TimeoutStopSec=60 {PYTHON} -u {REMOTE}/evaluate.py serve
lora_deadline=$(( $(date +%s) + 600 ))
until curl -sf -m 5 http://127.0.0.1:18821/health > {REMOTE}/evaluation/health.json; do
 systemctl is-active --quiet ac-liquid-lora-eval || exit 1
 test "$(date +%s)" -lt "$lora_deadline" || exit 2
 sleep 5
done
{PYTHON} -u {REMOTE}/evaluate.py run > {REMOTE}/evaluate.log 2>&1
'''
    submit("paired-final-evaluation-v1", script, 7200)
    await_operation("paired-final-evaluation-v1", "evaluation")
    subprocess.run([sys.executable, str(HERE/"analyze.py")], check=True)
    save(ROOT/"completion.json", {"status": "complete", "ec2": "kept_running",
                                 "github_push": False, "production_deployed": False})
    print("ALL_FROZEN_STAGES_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
