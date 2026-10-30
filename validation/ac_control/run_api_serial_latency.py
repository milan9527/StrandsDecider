"""Extend the frozen per-Key serial diagnostic to Jev and GPT, sequentially."""

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import boto3
import httpx
from api_ablation_protocol import GPT_MODEL, GPT_SYSTEM
from botocore.config import Config
from resume_api_capture import encode_binary
from run_api_ablation import invoke
from run_resident import save, sha, stamp


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schedule(payload, repetitions):
    for repetition in range(-1, repetitions):
        modes = (["full_30"] if repetition == -1
                 else ["full_30", "serial_1"] if repetition % 2 == 0
                 else ["serial_1", "full_30"])
        for mode in modes:
            tasks = ([payload] if mode == "full_30" else [
                {"state": payload["state"], "questions": {key: question}}
                for key, question in payload["questions"].items()
            ])
            for task in tasks:
                yield repetition, mode, task


def prepare(run, parent, api_parent):
    if run.exists():
        raise FileExistsError("Refusing to overwrite an existing run")
    parent_plan = json.loads((parent / "plan.json").read_text())
    api_plan = json.loads((api_parent / "plan.json").read_text())
    payload = json.loads((parent / "payload.json").read_text())
    assert sha(payload) == parent_plan["payload_sha256"]
    assert len(payload["questions"]) == 30 and parent_plan["repetitions"] == 3
    run.mkdir(parents=True)
    (run / "payload.json").write_bytes((parent / "payload.json").read_bytes())
    sources = run / "sources"
    sources.mkdir()
    source_names = [
        "run_api_serial_latency.py", "analyze_api_serial_latency.py",
        "run_api_ablation.py", "api_ablation_protocol.py", "resume_api_capture.py",
        "run_resident.py", "run_ablation.py", "ablation_protocol.py", "analyze.py",
    ]
    for name in source_names:
        (sources / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    plan = {
        "prepared_at": stamp(), "case_id": parent_plan["case_id"],
        "payload_sha256": sha(payload), "repetitions": parent_plan["repetitions"],
        "warmup_per_provider": 1, "providers": ["jev", "gpt"],
        "modes": ["full_30", "serial_1"], "outer_concurrency": 1,
        "single_question_concurrency": 1, "automatic_retries": 0,
        "online_output_repair": False,
        "model_order": "jev completes before gpt starts; no overlapping model windows",
        "state_policy": parent_plan["state_policy"],
        "scoring_policy": parent_plan["scoring_policy"],
        "client_host": platform.node(),
        "client_host_policy": "Existing authorized API test host, as in the original API comparison; "
                              "GPU serial diagnostic used a separate GPU host and loopback",
        "region": api_plan["region"],
        "jev_secret_arn": api_plan["jev_secret_arn"],
        "jev_request_model": api_plan["jev_request_model"],
        "jev_expected_response_model": "jev-1.14.0",
        "gpt_model": GPT_MODEL, "gpt_effort": "low",
        "gpt_max_output_tokens": 8192, "gpt_formatting_system": GPT_SYSTEM,
        "transport": "Jev native HTTPS via persistent httpx; GPT Bedrock Converse via boto3",
        "cache_policy": "No explicit cache controls; record native usage without inferring hidden caching",
        "parent_run_name": parent.name,
        "parent_files_sha256": {name: digest(parent / name) for name in [
            "plan.json", "payload.json", "receipts.jsonl", "summary.json",
        ]},
        "api_parent_run_name": api_parent.name,
        "api_parent_plan_sha256": digest(api_parent / "plan.json"),
        "source_sha256": {name: digest(sources / name) for name in source_names},
    }
    save(run / "plan.json", plan)
    print(json.dumps({"run": str(run), "payload_sha256": sha(payload),
                      "planned_formal_calls": 186, "planned_warmup_calls": 2}))


def run_test(run):
    plan = json.loads((run / "plan.json").read_text())
    payload = json.loads((run / "payload.json").read_text())
    assert sha(payload) == plan["payload_sha256"]
    for name, expected in plan["source_sha256"].items():
        assert digest(Path(__file__).with_name(name)) == expected, name
    if (run / "receipts.jsonl").exists():
        raise FileExistsError("Refusing to replay saved observations")
    save(run / "client_environment.json", {
        "recorded_at": stamp(), "python": sys.version, "platform": platform.platform(),
        "boto3": boto3.__version__, "httpx": httpx.__version__,
        "hostname": platform.node(), "region": plan["region"],
    })
    config = Config(connect_timeout=10, read_timeout=180, retries={"total_max_attempts": 1})
    profile = boto3.client("bedrock", region_name=plan["region"], config=config).get_inference_profile(
        inferenceProfileIdentifier=GPT_MODEL)
    save(run / "bedrock_profile.json", json.loads(json.dumps(profile, default=str)))
    assert profile["status"] == "ACTIVE"
    metadata = {
        "started_at": stamp(), "status": "running", "actual_calls": 0,
        "formal_calls": 0, "errors": 0, "automatic_retries": 0,
        "outer_concurrency": 1, "provider_windows": {},
        "plan_sha256": digest(run / "plan.json"),
    }
    save(run / "run.json", metadata)
    try:
        with (run / "receipts.jsonl").open("x") as stream:
            for provider in plan["providers"]:
                if provider == "jev":
                    secret = boto3.client(
                        "secretsmanager", region_name=plan["region"], config=config
                    ).get_secret_value(SecretId=plan["jev_secret_arn"])["SecretString"].strip()
                    client = httpx.Client(
                        headers={"Authorization": "Bearer " + secret},
                        timeout=httpx.Timeout(180, connect=10), trust_env=False,
                        follow_redirects=False,
                    )
                    del secret
                else:
                    client = boto3.client("bedrock-runtime", region_name=plan["region"], config=config)
                metadata["provider_windows"][provider] = {"started_at": stamp()}
                try:
                    for repetition, mode, task in schedule(payload, plan["repetitions"]):
                        row = {
                            "provider": provider, "mode": mode, "repetition": repetition,
                            "warmup": repetition == -1, "question_ids": list(task["questions"]),
                            **invoke(provider, client, task, plan["jev_expected_response_model"]),
                            "finished_at": stamp(),
                        }
                        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"),
                                                allow_nan=False, default=encode_binary) + "\n")
                        stream.flush()
                        metadata["actual_calls"] += 1
                        metadata["formal_calls"] += not row["warmup"]
                        metadata["errors"] += row["status"] != "ok"
                        metadata["last_provider"] = provider
                        metadata["last_mode"] = mode
                        metadata["last_repetition"] = repetition
                        save(run / "run.json", metadata)
                        print(json.dumps({
                            "provider": provider, "repetition": repetition, "mode": mode,
                            "question_ids": row["question_ids"] if mode == "serial_1" else ["all_30"],
                            "status": row["status"], "client_ms": row["client_ms"],
                            "completed": metadata["actual_calls"],
                        }), flush=True)
                        if row["warmup"] and row["status"] != "ok":
                            raise RuntimeError("Warmup failed; saved evidence, no formal calls or retries")
                finally:
                    client.close()
                    metadata["provider_windows"][provider]["finished_at"] = stamp()
        metadata["status"] = "complete" if metadata["errors"] == 0 else "complete_with_errors"
        metadata["finished_at"] = stamp()
    finally:
        save(run / "run.json", metadata)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--api-parent", type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.run, args.parent, args.api_parent)
    else:
        run_test(args.run)
