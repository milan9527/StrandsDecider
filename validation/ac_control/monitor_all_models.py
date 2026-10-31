"""Read saved progress and S3 checkpoints without contacting the GPU services."""

import json

import boto3
from all_models_protocol import PROVIDERS, ROOT


def progress():
    state = json.loads((ROOT / "gpu-controller-tokyo.json").read_text())
    completed = []
    for provider in PROVIDERS:
        path = ROOT / "results" / provider / "run.json"
        if path.exists():
            meta = json.loads(path.read_text())
            if meta["status"] in ("complete", "complete_with_errors") and meta["calls"] == 2049:
                completed.append(provider)
    result = {"completed": completed, "controller": {
        key: state[key] for key in ("status", "phase", "provider", "error") if key in state}}
    if state["status"] == "running" and state["phase"] == "benchmark":
        client = boto3.client("s3", region_name="us-east-1")
        try:
            response = client.get_object(
                Bucket="strands-decider-vllm-632930644527",
                Key=f"output/ac-all-models/2026-10-30-full-v1/results/{state['provider']}/run.json",
            )
        except client.exceptions.NoSuchKey:
            result["checkpoint"] = "First upload pending"
        else:
            meta = json.loads(response["Body"].read())
            result["checkpoint"] = {k: meta.get(k) for k in ("status", "calls", "errors", "last")}
            result["checkpoint"]["uploaded_at"] = response["LastModified"].isoformat()
    return result


if __name__ == "__main__":
    print(json.dumps(progress(), ensure_ascii=False))
