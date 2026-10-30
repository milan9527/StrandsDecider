"""Apply bounded H2O runtime trials with an automatic return to the saved service."""

import argparse
import hashlib
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SERVICE = "decider-h2o"
DROPIN = Path("/etc/systemd/system/decider-h2o.service.d/90-ac-optimization.conf")
GUARD = "ac-h2o-optimization-rollback"
PROTECTED = ["decider-vllm", "decider-liquid", "decider-comparison-gateway"]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def command(args, timeout=30, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("Command failed: " + " ".join(args) + "\n" + result.stderr[-2000:])
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def protected_state():
    return command(["systemctl", "show", *PROTECTED,
                    "--property=Id,ActiveState,SubState,NRestarts,ExecMainStartTimestamp"])["stdout"]


def health():
    try:
        with urllib.request.urlopen("http://127.0.0.1:18803/health", timeout=3) as response:
            result = json.load(response)
            return result if result.get("ok") and result.get("model") == "h2oai/h2o-lightning-4b" else None
    except (OSError, ValueError):
        return None


def wait_ready(timeout):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        result = health()
        if result:
            return result
        state = command(["systemctl", "is-active", SERVICE], check=False)["stdout"].strip()
        if state in ("failed", "inactive"):
            raise RuntimeError("H2O stopped during startup: " + state)
        time.sleep(5)
    raise TimeoutError("H2O startup did not finish within the trial limit")


def backup(root):
    directory = root / "rollback"
    if (directory / "original.json").exists():
        return json.loads((directory / "original.json").read_text())
    if DROPIN.exists():
        raise FileExistsError("An unrelated optimization drop-in already exists")
    effective = command(["systemctl", "cat", SERVICE])["stdout"]
    starts = [line for line in effective.splitlines() if line.startswith("ExecStart=")]
    assert len(starts) == 1 and "--max-num-seqs 1 " in starts[0]
    assert "--enforce-eager" in starts[0] and "--quantization fp8" in starts[0]
    original = {
        "saved_at": stamp(), "effective_unit": effective, "exec_start": starts[0],
        "protected_services": protected_state(), "original_dropin_existed": False,
        "health": health(),
    }
    assert original["health"]
    save(directory / "original.json", original)
    (directory / "decider-h2o.service.original").write_text(effective)
    return original


def disarm_guard():
    command(["systemctl", "stop", GUARD + ".timer"], check=False)
    command(["systemctl", "reset-failed", GUARD + ".service"], check=False)


def arm_guard(root):
    disarm_guard()
    command([
        "systemd-run", "--collect", "--unit=" + GUARD, "--on-active=25m",
        "--timer-property=AccuracySec=1s", "/usr/bin/python3", str(Path(__file__).resolve()),
        "rollback", "--root", str(root), "--from-guard",
    ])


def rollback(root, from_guard=False):
    if not from_guard:
        disarm_guard()
    original = json.loads((root / "rollback" / "original.json").read_text())
    if DROPIN.exists():
        DROPIN.unlink()
    command(["systemctl", "daemon-reload"])
    command(["systemctl", "restart", SERVICE], timeout=90)
    restored = wait_ready(600)
    assert protected_state() == original["protected_services"], "Another service changed"
    save(root / "rollback" / ("guard_restored.json" if from_guard else "restored.json"), {
        "restored_at": stamp(), "health": restored, "protected_services_unchanged": True,
    })
    return restored


def configure(args):
    original = backup(args.root)
    assert protected_state() == original["protected_services"]
    directory = args.root / "runtime_trials" / args.variant
    if directory.exists():
        raise FileExistsError("Trial already exists")
    directory.mkdir(parents=True)
    line = original["exec_start"].replace("--max-num-seqs 1 ", f"--max-num-seqs {args.sequences} ")
    cache = f"/bench/h2o-cache/ac-optimization-{args.variant}"
    line = line.replace("VLLM_CACHE_ROOT=/bench/h2o-cache", "VLLM_CACHE_ROOT=" + cache)
    if args.graphs == "on":
        line = line.replace(" --enforce-eager", "")
        line = line.replace(" -e VLLM_CACHE_ROOT=",
                            " -e TORCHINDUCTOR_COMPILE_THREADS=1 -e VLLM_CACHE_ROOT=")
    if args.gdn_tokens:
        line = line.replace("VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS=0",
                            f"VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS={args.gdn_tokens}")
        line = line.replace("VLLM_GDN_PREFILL_GRAPH_PRECAPTURE=0",
                            "VLLM_GDN_PREFILL_GRAPH_PRECAPTURE=1")
        line = line.replace(" -e VLLM_CACHE_ROOT=",
                            f" -e VLLM_GDN_PREFILL_GRAPH_MAX_SEQS={args.sequences} -e VLLM_CACHE_ROOT=")
    override = "[Service]\nExecStart=\n" + line + "\nRestart=no\n"
    save(directory / "trial_plan.json", {
        "prepared_at": stamp(), "sequences": args.sequences, "graphs": args.graphs,
        "gdn_graph_max_tokens": args.gdn_tokens,
        "gdn_graph_max_sequences": args.sequences if args.gdn_tokens else None,
        "compiler_threads": 1 if args.graphs == "on" else None,
        "startup_timeout_seconds": args.timeout,
        "mode": "bidirectional remains default; causal only by explicit request",
        "override": override, "cache_directory": cache,
        "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    })
    arm_guard(args.root)
    DROPIN.parent.mkdir(parents=True, exist_ok=True)
    DROPIN.write_text(override)
    metadata = {"started_at": stamp(), "status": "starting"}
    save(directory / "result.json", metadata)
    try:
        command(["systemctl", "daemon-reload"])
        command(["systemctl", "restart", SERVICE], timeout=90)
        metadata["health"] = wait_ready(args.timeout)
        assert metadata["health"]["attention_mode"] == "bidirectional"
        assert protected_state() == original["protected_services"], "Another service changed"
        metadata.update(status="ready", ready_at=stamp(), protected_services_unchanged=True)
    except BaseException as error:
        metadata.update(status="failed", error_type=type(error).__name__, error=str(error))
        save(directory / "failure_logs.json",
             command(["docker", "logs", "--tail", "180", "decider-h2o-resident"], check=False))
        save(directory / "result.json", metadata)
        rollback(args.root)
        metadata["rolled_back"] = True
        raise
    finally:
        metadata["gpu"] = command([
            "nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader",
        ], check=False)
        save(directory / "result.json", metadata)
    print(json.dumps(metadata), flush=True)


def accept(root):
    original = json.loads((root / "rollback" / "original.json").read_text())
    assert protected_state() == original["protected_services"]
    assert health()
    override = DROPIN.read_text()
    assert "Restart=no\n" in override
    DROPIN.write_text(override.replace("Restart=no\n", "Restart=always\n"))
    command(["systemctl", "daemon-reload"])
    disarm_guard()
    save(root / "accepted_runtime.json", {
        "accepted_at": stamp(), "override": DROPIN.read_text(), "health": health(),
        "protected_services_unchanged": True, "rollback": str(root / "rollback"),
    })
    print("Accepted current runtime; normal restart policy restored; rollback backup retained.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["configure", "rollback", "accept"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--variant")
    parser.add_argument("--sequences", type=int, choices=[1, 2, 4], default=1)
    parser.add_argument("--graphs", choices=["off", "on"], default="off")
    parser.add_argument("--gdn-tokens", type=int, choices=[0, 2048, 4096], default=0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--from-guard", action="store_true")
    args = parser.parse_args()
    if args.action == "configure":
        assert args.variant and "/" not in args.variant and ".." not in args.variant
        configure(args)
    elif args.action == "rollback":
        rollback(args.root, args.from_guard)
    else:
        accept(args.root)
