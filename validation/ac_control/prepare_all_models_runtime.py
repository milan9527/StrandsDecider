"""Transfer answer-free inputs and prepare runtimes on the dedicated test host."""

import argparse
import io
import json
import shlex
import tarfile
from pathlib import Path

import boto3
from all_models_infra import BUCKET, PREFIX, REMOTE, ROOT, submit
from all_models_protocol import SOURCE_NAMES, digest, save, stamp

HERE = Path(__file__).parent
IMAGE = "632930644527.dkr.ecr.us-east-1.amazonaws.com/strands-decider-vllm@sha256:0bd44d374991dc8782b93d58bb41b3aab63fa0d242149578b342cb139f371d07"


def transfer():
    files = {name: ROOT / "sources" / name for name in SOURCE_NAMES}
    files.update({name: ROOT / name for name in ("plan.json", "cases.json", "models.json", "schedule.json")})
    files["candidate_server.py"] = HERE / "candidate_server.py"
    files["liquid_server.py"] = HERE.parents[1] / "deployment/open_models/liquid_server.py"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, path in files.items():
            assert path.exists() and name not in ("references.json", "spec_references.json", "spec.md")
            archive.add(path, arcname=name)
    artifact = ROOT / "runtime-input.tar.gz"
    assert not artifact.exists(), "Do not overwrite runtime transfer"
    artifact.write_bytes(stream.getvalue())
    key = "input/" + PREFIX + "/runtime-input.tar.gz"
    boto3.client("s3", region_name="us-east-1").put_object(
        Bucket=BUCKET, Key=key, Body=artifact.read_bytes(), ServerSideEncryption="AES256")
    save(ROOT / "runtime-transfer.json", {
        "created_at": stamp(), "bucket": BUCKET, "key": key,
        "sha256": digest(artifact), "files": {name: digest(path) for name, path in files.items()},
        "reference_answers_in_archive": False,
    })
    return {"files": len(files), "sha256": digest(artifact)}


def bootstrap():
    transfer = json.loads((ROOT / "runtime-transfer.json").read_text())
    script = "\n".join([
        "set -euo pipefail",
        # The clone is a dedicated benchmark host, never the resident service instance.
        "test -d /opt/ac-candidate-tests/models",
        "test ! -d " + REMOTE,
        "mkdir -p " + REMOTE + "/run " + REMOTE + "/logs " + REMOTE + "/models",
        "systemctl stop apt-daily.timer apt-daily-upgrade.timer fwupd-refresh.timer update-notifier-download.timer || true",
        "systemctl mask --runtime apt-daily.service apt-daily-upgrade.service fwupd-refresh.service update-notifier-download.service",
        "maintenance_deadline=$(( $(date +%s) + 1800 ))",
        "while systemctl is-active --quiet apt-daily.service || systemctl is-active --quiet apt-daily-upgrade.service; do",
        ' test "$(date +%s)" -lt "$maintenance_deadline" || exit 3',
        " sleep 10",
        "done",
        "test -z \"$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)\"",
        "ln -s /opt/ac-candidate-tests/envs " + REMOTE + "/envs",
        "ln -s /opt/ac-candidate-tests/cache " + REMOTE + "/cache",
        "cp /opt/ac-candidate-tests/models-verified.json " + REMOTE + "/models-verified.json",
        "cp /opt/ac-candidate-tests/logs/*requirements.txt " + REMOTE + "/logs/",
        "cp /opt/ac-candidate-tests/logs/h2o-overlay-verification.json " + REMOTE + "/logs/",
        *["ln -s /opt/ac-candidate-tests/models/" + p + " " + REMOTE + "/models/" + p
          for p in ("pplx", "knowline", "torchcast", "clef", "h2o")],
        "aws s3 cp s3://" + BUCKET + "/" + transfer["key"] + " " + REMOTE + "/runtime-input.tar.gz --only-show-errors",
        "python3 - <<'CHECK'",
        "import hashlib,tarfile",
        f"path={REMOTE + '/runtime-input.tar.gz'!r}",
        f"assert hashlib.sha256(open(path,'rb').read()).hexdigest()=={transfer['sha256']!r}",
        "with tarfile.open(path) as archive:",
        " assert all(m.isfile() and '/' not in m.name for m in archive.getmembers())",
        f" archive.extractall({REMOTE + '/run'!r}, filter='data')",
        "CHECK",
        "/opt/ac-candidate-tests/tools/bin/uv venv --python /usr/bin/python3 " + REMOTE + "/runner-env",
        "/opt/ac-candidate-tests/tools/bin/uv pip install --python " + REMOTE + "/runner-env/bin/python boto3 httpx",
        "/opt/ac-candidate-tests/tools/bin/uv pip freeze --python " + REMOTE
        + "/runner-env/bin/python > " + REMOTE + "/logs/runner-requirements.txt",
        "aws s3 sync s3://" + BUCKET + "/input/model/ " + REMOTE + "/models/decider --only-show-errors",
        "aws s3 sync s3://" + BUCKET + "/input/" + PREFIX + "/models/liquid/ "
        + REMOTE + "/models/liquid --only-show-errors",
        "aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "
        "632930644527.dkr.ecr.us-east-1.amazonaws.com",
        "docker pull " + IMAGE,
        "docker image inspect " + IMAGE + " --format '{{.Id}}' > " + REMOTE + "/logs/strands-image-id.txt",
        "docker logout 632930644527.dkr.ecr.us-east-1.amazonaws.com",
        "docker run --rm --memory=4g -v " + REMOTE + "/models/decider:/models/decider-vllm:ro "
        + IMAGE + " verify-artifacts --model /models/decider-vllm > " + REMOTE + "/logs/strands-model-integrity.json",
        "python3 - <<'VERIFY'",
        "import hashlib,json,pathlib",
        f"base=pathlib.Path({REMOTE + '/models'!r})",
        "result={}",
        "for name in ['liquid','pplx','knowline','torchcast','clef','h2o']:",
        " manifest=json.loads((base/name/'manifest.json').read_text())",
        " for item in manifest['files']:",
        "  path=base/name/item['path']",
        "  h=hashlib.sha256()",
        "  with path.open('rb') as f:",
        "   for chunk in iter(lambda:f.read(4*1024*1024),b''): h.update(chunk)",
        "  assert h.hexdigest()==item['sha256'],str(path)",
        " result[name]={'revision':manifest['revision'],'verified_files':len(manifest['files'])}",
        f"pathlib.Path({REMOTE + '/logs/model-verification.json'!r}).write_text(json.dumps(result,indent=2))",
        "VERIFY",
        "/opt/ac-candidate-tests/envs/h2o/bin/python - <<'OVERLAY'",
        "import hashlib,json,pathlib,sysconfig",
        f"path=pathlib.Path({REMOTE + '/logs/h2o-overlay-verification.json'!r})",
        "expected=json.loads(path.read_text())",
        "site=pathlib.Path(sysconfig.get_paths()['purelib'])",
        "assert len(expected)==30",
        "assert all(hashlib.sha256((site/name).read_bytes()).hexdigest()==sha for name,sha in expected.items())",
        f"pathlib.Path({REMOTE + '/logs/h2o-overlay-rechecked.json'!r}).write_text(json.dumps(expected,indent=2))",
        "OVERLAY",
        # Match Liquid's resident runtime by using the same image and the cloned H2O env.
        "docker run --rm --entrypoint /bench/envs/h2o/bin/python -v " + REMOTE + ":/bench "
        "-v /opt/ac-candidate-tests:/opt/ac-candidate-tests:ro "
        + IMAGE + " -c 'import torch,transformers; print(torch.__version__,transformers.__version__)'"
        " > " + REMOTE + "/logs/liquid-runtime-packages.txt",
        "df -h / > " + REMOTE + "/logs/storage.txt",
        "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > " + REMOTE + "/logs/gpu.csv",
        "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX + "/logs --only-show-errors",
    ])
    return submit("prepare-complete-runtime", "bash -c " + shlex.quote(script), 5400)


def launch(provider, attempt="nine-models"):
    if provider not in ("decider", "liquid"):
        import launch_candidate
        launch_candidate.REMOTE = REMOTE
        launch_candidate.PREFIX = PREFIX

        def submit_native(name, script, timeout):
            if provider == "knowline":
                # This changes routing/health identity only, not the model's prompts or scoring.
                assert script.count("--served-model-name m") == 2
                script = script.replace("--served-model-name m", "--served-model-name PelaAI/KnowLine-4B-Gen5.5")
            return submit(name, script, timeout)

        launch_candidate.submit = submit_native
        return launch_candidate.launch(provider, attempt)
    unit = "ac-nine-" + provider
    docker = ["docker", "run", "--rm", "--name", unit, "--gpus", "all", "--network", "host",
              "--shm-size=2g", "--memory=6g", "--cpuset-cpus=0-3",
              "--cap-drop=ALL", "--security-opt=no-new-privileges:true"]
    if provider == "decider":
        docker += ["-v", REMOTE + "/models/decider:/models/decider-vllm:ro",
                   "-v", REMOTE + "/decider-cache:/root/.cache", IMAGE,
                   "serve", "--model", "/models/decider-vllm", "--host", "127.0.0.1", "--port", "18811",
                   "--max-num-seqs", "1", "--max-inflight-questions", "1", "--max-pending-requests", "32",
                   "--max-num-batched-tokens", "8192", "--gpu-memory-utilization", "0.26",
                   "--timeout-seconds", "25"]
    else:
        docker += ["--entrypoint", "/bench/envs/h2o/bin/python",
                   "-v", REMOTE + ":/bench", "-v", "/opt/ac-candidate-tests:/opt/ac-candidate-tests:ro",
                   IMAGE, "/bench/run/liquid_server.py", "--model", "/bench/models/liquid"]
    endpoint = "http://127.0.0.1:" + ("18801" if provider == "liquid" else "18811")
    script = "\n".join([
        "set -eu",
        "test -s " + REMOTE + "/logs/model-verification.json",
        "test -z \"$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)\"",
        shlex.join(["systemd-run", "--unit", unit, "--property=Restart=no",
                    "--property=KillMode=control-group", "--property=TimeoutStopSec=60", *docker]),
        "candidate_deadline=$(( $(date +%s) + 1800 ))",
        "until curl -sf -m 5 " + endpoint + "/health > " + REMOTE + "/logs/" + provider + "-health-startup.json; do",
        " systemctl is-active --quiet " + unit + " || exit 1",
        ' test "$(date +%s)" -lt "$candidate_deadline" || exit 2',
        " sleep 10",
        "done",
        "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX + "/logs --only-show-errors",
    ])
    return submit("start-" + provider + "-" + attempt, script, 2000)


def benchmark(provider, attempt="nine-models"):
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
    script = "\n".join([
        "set -eu",
        "trap " + shlex.quote(cleanup) + " EXIT",
        "systemctl is-active --quiet " + unit,
        shlex.join([REMOTE + "/runner-env/bin/python", "-u", REMOTE + "/run/run_all_models.py",
                    "--run", REMOTE + "/run", "--provider", provider, "--endpoint", endpoint,
                    "--s3-output", "s3://" + BUCKET + "/output/" + PREFIX + "/results"]),
    ])
    return submit("benchmark-" + provider + "-" + attempt, script, 10800)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("transfer", "bootstrap", "launch", "benchmark"))
    parser.add_argument("--provider")
    args = parser.parse_args()
    result = (transfer() if args.action == "transfer" else bootstrap() if args.action == "bootstrap"
              else launch(args.provider) if args.action == "launch" else benchmark(args.provider))
    print(json.dumps(result, indent=2))
