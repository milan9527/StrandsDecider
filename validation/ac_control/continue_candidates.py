"""Resume completed operations without duplicating inference; stop on first failure."""

import argparse
import json
import time

from benchmark_candidate import benchmark
from launch_candidate import launch
from remote_candidates import BUCKET, PREFIX, REMOTE, ROOT, collect, status, submit


def wait(name):
    while True:
        try:
            result = status(name)
        except Exception as error:
            if getattr(error, "response", {}).get("Error", {}).get("Code") != "InvocationDoesNotExist":
                raise
            time.sleep(3)
            continue
        print(name, result["Status"], flush=True)
        if result["Status"] not in ("Pending", "InProgress", "Delayed"):
            collect()
            assert result["Status"] == "Success", name + ": " + json.dumps(result)
            return
        time.sleep(30)


def run(providers, attempt="official-1"):
    for provider in providers:
        if provider == "clef":
            name = "prepare-clef-fast-dependencies"
            if not (ROOT / "operations" / (name + ".json")).exists():
                # Executed only after the previous benchmark has stopped its model.
                # Qwen3VLProcessor requires torchvision; enable the optional native convolution kernel too.
                script = "\n".join([
                    "set -eu",
                    'test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"',
                    "export UV_CACHE_DIR=" + REMOTE + "/uv-cache",
                    "export CUDA_HOME=/usr/local/cuda-13.0",
                    "export PATH=" + REMOTE + "/envs/clef/bin:/usr/local/cuda-13.0/bin:$PATH",
                    "export MAX_JOBS=2",
                    REMOTE + "/tools/bin/uv pip install --python " + REMOTE
                    + "/envs/clef/bin/python 'torch==2.11.0' 'torchvision==0.26.0' ninja packaging wheel setuptools",
                    REMOTE + "/tools/bin/uv pip install --python " + REMOTE
                    + "/envs/clef/bin/python --no-build-isolation 'causal-conv1d==1.7.0'",
                    REMOTE + "/tools/bin/uv pip freeze --python " + REMOTE
                    + "/envs/clef/bin/python > " + REMOTE + "/logs/clef-final-requirements.txt",
                    "aws s3 sync " + REMOTE + "/logs s3://" + BUCKET + "/output/" + PREFIX
                    + "/logs --only-show-errors",
                ])
                submit(name, script, 1800)
            wait(name)
        name = "start-" + provider + "-" + attempt
        if not (ROOT / "operations" / (name + ".json")).exists():
            launch(provider, attempt)
        wait(name)
        name = "benchmark-" + provider + "-" + attempt
        if not (ROOT / "operations" / (name + ".json")).exists():
            benchmark(provider, attempt)
        wait(name)
    print("All requested model runs complete; verify artifacts before stopping the EC2.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("providers", nargs="+")
    parser.add_argument("--attempt", default="official-1")
    args = parser.parse_args()
    run(args.providers, args.attempt)
