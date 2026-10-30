"""Read-only post-test inventory on the isolated GPU, excluding reference answers."""

import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def command(args):
    result = subprocess.run(args, text=True, capture_output=True, check=False, timeout=30)
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def inventory(root):
    assert not (root / "run/references.json").exists()
    processes = command(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"])
    assert processes["returncode"] == 0 and not processes["stdout"].strip(), "A GPU model is still resident"
    models = {}
    for folder in sorted((root / "models").iterdir()):
        path = folder / "manifest.json"
        manifest = json.loads(path.read_text())
        checks = {}
        for item in manifest["files"]:
            target = folder / item["path"]
            assert target.stat().st_size == item["bytes"]
            # All artifacts were SHA-256 verified before startup. Recheck executable/configuration sources here.
            if target.suffix in (".py", ".sh", ".json", ".patch", ".jinja", ".toml") or target.name.endswith("SHA256SUMS"):
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                assert digest == item["sha256"], str(target)
                checks[item["path"]] = digest
        models[folder.name] = {
            "repository": manifest["model"], "revision": manifest["revision"],
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "all_artifact_sizes_match": True, "source_sha256_rechecked": checks,
        }
    units = ["ac-candidate-" + name for name in models]
    unit_state = command(["systemctl", "show", *units,
                          "--property=Id,LoadState,ActiveState,SubState,Result,ExecMainStatus"])
    assert "ActiveState=active" not in unit_state["stdout"]
    data = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "benchmark_reference_file_absent": True,
        "gpu_processes": processes,
        "gpu": command(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version",
                        "--format=csv,noheader"]),
        "units": unit_state,
        "stop_guard": command(["systemctl", "show", "ac-candidate-fixed-stop.timer",
                              "--property=ActiveState,NextElapseUSecRealtime"]),
        "automatic_maintenance": command(["systemctl", "show", "apt-daily.service", "apt-daily-upgrade.service",
                                          "--property=Id,LoadState,ActiveState,UnitFileState"]),
        "models": models,
        "initial_all_artifact_sha256_verification": json.loads((root / "models-verified.json").read_text()),
        "frozen_inputs": {name: hashlib.sha256((root / "run" / name).read_bytes()).hexdigest()
                          for name in ("cases.json", "models.json", "plan.json", "command_set.json",
                                       "candidate_server.py", "run_candidate_benchmark.py")},
        "disk": command(["df", "-h", str(root)]),
        "inventory_python": platform.python_version(),
    }
    target = root / "logs/final-inventory.json"
    target.write_text(json.dumps(data, indent=2) + "\n")
    return data


if __name__ == "__main__":
    inventory(Path("/opt/ac-candidate-tests"))
