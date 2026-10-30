"""Start one native model runtime; all model processes belong to one systemd unit."""

import argparse
import shlex

from remote_candidates import BUCKET, PREFIX, REMOTE, submit


def launch(provider, attempt):
    unit = "ac-candidate-" + provider
    python = REMOTE + "/envs/" + provider + "/bin/python"
    model = REMOTE + "/models/" + provider
    env = {
        "PATH": REMOTE + "/envs/" + provider + "/bin:/usr/local/cuda-13.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
        "TORCHINDUCTOR_COMPILE_THREADS": "1", "TOKENIZERS_PARALLELISM": "false",
        "TRITON_CACHE_DIR": REMOTE + "/cache/" + provider + "/triton",
        "TORCHINDUCTOR_CACHE_DIR": REMOTE + "/cache/" + provider + "/inductor",
        "CUDA_HOME": "/usr/local/cuda-12.8" if provider == "torchcast" else "/usr/local/cuda-13.0",
    }
    if provider in ("pplx", "torchcast", "clef"):
        command = [python, REMOTE + "/run/candidate_server.py", "--provider", provider,
                   "--model", model, "--cases", REMOTE + "/run/cases.json",
                   "--metadata", REMOTE + "/logs/" + provider + "-runtime.json", "--port", "18811"]
    elif provider == "knowline":
        # Same official launch arguments, plus loopback binding of the engine.
        command = ["bash", "-c", "\n".join([
            "set -euo pipefail",
            shlex.join([python, "-m", "sglang.launch_server", "--model-path", model,
                        "--served-model-name", "m", "--tp", "1", "--quantization", "fp8",
                        "--mem-fraction-static", "0.72", "--mamba-radix-cache-strategy", "extra_buffer",
                        "--enable-fp32-lm-head", "--host", "127.0.0.1", "--port", "18812"]) + " &",
            "engine_pid=$!",
            "trap 'kill \"$engine_pid\" 2>/dev/null || true' EXIT",
            'until curl -sf -m 3 http://127.0.0.1:18812/health >/dev/null; do sleep 5; kill -0 "$engine_pid"; done',
            shlex.join([python, model + "/knowline_server.py", "--model", model, "--backend", "sglang",
                        "--url", "http://127.0.0.1:18812", "--served-model-name", "m",
                        "--temperature", "1", "--workers", "16", "--host", "127.0.0.1", "--port", "18811"]),
        ])]
    else:
        env.update(MODEL=model, PORT="18811", VLLM_PORT="18802", MAX_LEN="4096", GPU_UTIL="0.34",
                   MAX_IMAGES="1", MAX_PIXELS="65536", CUDA_GRAPH_MAX_TOKENS="128",
                   VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS="0", VLLM_GDN_PREFILL_GRAPH_PRECAPTURE="0",
                   VLLM_CACHE_ROOT=REMOTE + "/cache/h2o/vllm", SHIM_CACHE_WRITE="all",
                   VLLM_ARGS="--max-num-seqs 1 --max-num-batched-tokens 4096 --enforce-eager --quantization fp8")
        command = ["bash", model + "/serve.sh"]
    invocation = ["systemd-run", "--unit", unit, "--property=Restart=no",
                  "--property=KillMode=control-group", "--property=TimeoutStopSec=45",
                  "--working-directory=" + model]
    invocation += ["--setenv=" + key + "=" + value for key, value in env.items()]
    invocation += command
    preflight = []
    if provider == "clef":
        # Check optional processor dependencies before loading the 9B backbone onto the GPU.
        preflight.append(shlex.join([
            python, "-c",
            "from transformers import AutoProcessor; "
            + f"p=AutoProcessor.from_pretrained({model!r}); print(type(p).__name__)",
        ]))
    script = "\n".join([
        "set -eu",
        # Infrastructure preparation must be finished before a model starts.
        "test -s " + REMOTE + "/models-verified.json",
        "test -s " + REMOTE + "/logs/pplx-requirements.txt",
        "test -s " + REMOTE + "/logs/h2o-overlay-verification.json",
        "test -z \"$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)\"",
        *preflight,
        shlex.join(invocation),
        "candidate_deadline=$(( $(date +%s) + 1800 ))",
        "trap " + shlex.quote(
            "journalctl -u " + unit + " --no-pager -o short-iso > "
            + REMOTE + "/logs/" + provider + "-" + attempt + "-startup.log\n"
            + "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX
            + "/logs --only-show-errors") + " EXIT",
        "until curl -sf -m 5 http://127.0.0.1:18811/health > "
        + REMOTE + "/logs/" + provider + "-health-startup.json; do",
        "  systemctl is-active --quiet " + unit + " || exit 1",
        '  test "$(date +%s)" -lt "$candidate_deadline" || exit 2',
        "  sleep 10",
        "done",
        "nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv",
    ])
    return submit("start-" + provider + "-" + attempt, script,2000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("pplx", "knowline", "torchcast", "clef", "h2o"))
    parser.add_argument("--attempt", default="official-1")
    args = parser.parse_args()
    print(launch(args.provider, args.attempt))
