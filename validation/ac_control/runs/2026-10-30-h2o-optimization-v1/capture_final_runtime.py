import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path("/opt/decider-open-models/ac-control/2026-10-30-h2o-optimization-v1")


def output(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=30, check=True).stdout


container = json.loads(output(["docker", "inspect", "decider-h2o-resident"]))[0]
env = dict(entry.split("=", 1) for entry in container["Config"]["Env"] if "=" in entry)
with urllib.request.urlopen("http://127.0.0.1:18803/health", timeout=5) as response:
    health = json.load(response)
timer = subprocess.run(["systemctl", "is-active", "ac-h2o-optimization-rollback.timer"],
                       capture_output=True, text=True, timeout=15)
result = {
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "health": health,
    "runtime": {
        "image": container["Image"], "started_at": container["State"]["StartedAt"],
        "restart_count": container["RestartCount"],
        "env": {key: env.get(key) for key in (
            "MAX_LEN", "GPU_UTIL", "VLLM_ARGS", "CUDA_GRAPH_MAX_TOKENS",
            "VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS", "VLLM_GDN_PREFILL_GRAPH_PRECAPTURE",
            "VLLM_GDN_PREFILL_GRAPH_MAX_SEQS", "TORCHINDUCTOR_COMPILE_THREADS",
            "VLLM_CACHE_ROOT", "SHIM_ATTENTION_MODE",
        )},
    },
    "protected_services": output([
        "systemctl", "show", "decider-vllm", "decider-liquid", "decider-comparison-gateway",
        "--property=Id,ActiveState,SubState,NRestarts,ExecMainStartTimestamp",
    ]),
    "effective_h2o_unit": output(["systemctl", "cat", "decider-h2o"]),
    "restart_policy": output(["systemctl", "show", "decider-h2o", "--property=Restart",
                              "--value"]).strip(),
    "rollback_timer_active": timer.stdout.strip() == "active",
    "optimization_dropin_exists": Path(
        "/etc/systemd/system/decider-h2o.service.d/90-ac-optimization.conf").exists(),
    "gpu": output(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                   "--format=csv,noheader"]),
    "memory": output(["free", "-m"]),
    "model_source_sha256": {
        name: hashlib.sha256((Path("/opt/decider-open-models/models/h2o") / name).read_bytes()).hexdigest()
        for name in ("serve.sh", "serve_config.json", "h2o_lightning_shim.py")
    },
}
assert health["ok"] and health["attention_mode"] == "bidirectional"
assert result["restart_policy"] == "always" and not result["rollback_timer_active"]
(root / "final_runtime.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
