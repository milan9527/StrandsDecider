"""Freeze an extension to Jev and GPT without touching the three-model evidence."""

import argparse
import hashlib
import json
from pathlib import Path

import boto3
from api_ablation_protocol import GPT_MODEL, GPT_SYSTEM, JEV_MODEL, JEV_URL
from run_resident import save, sha, stamp

HERE = Path(__file__).resolve().parent


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=False)
    parent_plan = json.loads((source / "plan.json").read_text())
    frozen = {}
    for name in ("experiments", "references", "command_set"):
        data = (source / (name + ".json")).read_bytes()
        value = json.loads(data)
        assert sha(value) == parent_plan[name + "_sha256"]
        (output / (name + ".json")).write_bytes(data)
        frozen[name + "_sha256"] = sha(value)
    source_dir = output / "sources"
    source_dir.mkdir()
    names = [
        "api_ablation_protocol.py", "run_api_ablation.py", "prepare_api_ablation.py",
        "analyze_api_ablation.py", "ablation_protocol.py", "run_ablation.py", "run_resident.py",
        "analyze.py", "analyze_ablation.py", "compare_resident.py", "prepare.py",
    ]
    for name in names:
        (source_dir / name).write_bytes((HERE / name).read_bytes())
    region = "us-east-1"
    stack = boto3.client("cloudformation", region_name=region).describe_stacks(
        StackName="strands-decider-demo",
    )["Stacks"][0]
    secret_arn = next(p["ParameterValue"] for p in stack["Parameters"] if p["ParameterKey"] == "JevSecretArn")
    profile = boto3.client("bedrock", region_name=region).get_inference_profile(
        inferenceProfileIdentifier=GPT_MODEL,
    )
    profile = {k: profile[k] for k in ("inferenceProfileId", "inferenceProfileName", "status", "type", "models")}
    assert profile["status"] == "ACTIVE" and profile["inferenceProfileId"] == GPT_MODEL
    assert all(x["modelArn"].endswith("/openai.gpt-6.1-sol") for x in profile["models"])
    save(output / "bedrock_profile.json", profile)
    prior_files = [
        "plan.json", "experiments.json", "references.json", "command_set.json", "ablation_results.json",
        "ablation_summary.json", "audit.json",
        *[f"{p}/formal_receipts.jsonl" for p in ("decider", "liquid", "h2o")],
    ]
    save(output / "plan.json", {
        "prepared_at": stamp(), "region": region, **frozen,
        "providers": ["jev", "gpt"], "arms": parent_plan["arms"],
        "parent_run": str(source.resolve()), "parent_files_sha256": {
            name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in prior_files
        },
        "new_observations_per_provider": 250, "maximum_new_calls_per_provider": 300,
        "baseline_policy": "Run all 250 observations for each new provider; reuse_baseline in inherited input is ignored.",
        "spec_cases": 20, "spec_orders": ["original", "reversed"],
        "extension_cases": 10, "extension_orders": ["original"],
        "extension_status": parent_plan["extension_status"],
        "jev_request_model": JEV_MODEL, "jev_url": JEV_URL, "jev_secret_arn": secret_arn,
        "jev_version_policy": "Pin formal response identity to the unique version returned by protocol preflight.",
        "gpt_model": GPT_MODEL, "gpt_effort": "low", "gpt_max_output_tokens": 8192,
        "gpt_formatting_system": GPT_SYSTEM, "gpt_output_mode": "Prompt-only JSON; no constrained decoder or semantic repair.",
        "gpt_model_identity_source": "Bedrock request modelId plus ACTIVE inference profile; Converse does not echo model ID.",
        "gpt_official_reference": "https://developers.openai.com/api/docs/models/gpt-6.1-sol",
        "automatic_retries": 0, "online_output_repair": False, "concurrency_per_provider": 1,
        "source_sha256": {name: hashlib.sha256((source_dir / name).read_bytes()).hexdigest() for name in names},
    })
    print("Frozen 250 observations/provider; all prior task payloads unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.output)
