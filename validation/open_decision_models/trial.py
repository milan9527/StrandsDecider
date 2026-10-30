"""Run one GPU model exclusively, retain failures, and stop its process afterward."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--h2o", action="store_true")
    args = parser.parse_args()
    root = Path("/bench")
    out = root / "results"
    out.mkdir(exist_ok=True)
    if (out / f"{args.provider}-quality.jsonl").exists():
        raise RuntimeError("Existing evidence: choose a separate trial directory before rerunning")
    used = int(subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        text=True).strip())
    if used > 512:
        raise RuntimeError(f"GPU is occupied before model startup: {used} MiB; stop competing services first")
    (out / f"{args.provider}-resource-check.json").write_text(json.dumps(
        {"gpu_memory_used_before_model_mib": used, "exclusive_round": True, "time_unix": time.time()},
        indent=2))
    env = dict(os.environ)
    if args.h2o:
        env.update(PATH=str(Path(args.python).parent) + ":" + env["PATH"], MAX_LEN="8192",
                   GPU_UTIL="0.88", PORT="18801", VLLM_PORT="18802", CUDA_GRAPH_MAX_TOKENS="128",
                   MAX_IMAGES="1", MAX_PIXELS="65536",
                   VLLM_GDN_PREFILL_GRAPH_MAX_TOKENS="0", VLLM_GDN_PREFILL_GRAPH_PRECAPTURE="0",
                   VLLM_ARGS="--max-num-seqs 16 --enforce-eager", VLLM_CACHE_ROOT="/bench/h2o-cache")
        command = ["bash", str(Path(args.model_path) / "serve.sh")]
    else:
        command = [args.python, str(root / "gpu_server.py"), "--provider", args.provider,
                   "--model-path", args.model_path]
    url = "http://127.0.0.1:18801"
    with (root / f"{args.provider}-server.log").open("w") as log:
        server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError(f"Model server exited with {server.returncode}; see server log")
                try:
                    health = requests.get(url + "/health", timeout=2)
                    if health.status_code == 200:
                        (out / f"{args.provider}-health.json").write_text(json.dumps(health.json(), indent=2))
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError("Model did not become ready within 15 minutes")
            for phase, concurrency in [("quality", 1), ("performance", 1), ("performance", 4), ("performance", 8)]:
                filename = f"{args.provider}-{phase}" + (f"-c{concurrency}" if phase == "performance" else "")
                subprocess.run([sys.executable, str(root / "run.py"), "--provider", args.provider,
                                "--requests", str(root / ("requests.json" if phase == "quality" else "performance_requests.json")),
                                "--output", str(out / (filename + ".jsonl")), "--url", url + "/v1/systemone",
                                "--phase", phase, "--concurrency", str(concurrency)], check=True)
            if args.provider == "liquid":
                with (out / "liquid-native-multiselect.jsonl").open("x") as stream:
                    for row in json.loads((root / "liquid_native_multiselect.json").read_text()):
                        started = time.perf_counter()
                        result = {"case_id": row["case_id"]}
                        try:
                            response = requests.post(url + "/v1/systemone", json=row["request"], timeout=90)
                            result["http_status"] = response.status_code
                            result["response_text"] = response.text
                            response.raise_for_status()
                            result["response"] = response.json()
                            result["status"] = "ok"
                        except Exception as exc:
                            result.update(status="error", error=f"{type(exc).__name__}: {exc}")
                        result["client_ms"] = (time.perf_counter() - started) * 1000
                        stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                        stream.flush()
        finally:
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            if server.poll() is None:
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait()
    (root / (args.provider + "-done")).write_text("complete\n")


if __name__ == "__main__":
    main()
