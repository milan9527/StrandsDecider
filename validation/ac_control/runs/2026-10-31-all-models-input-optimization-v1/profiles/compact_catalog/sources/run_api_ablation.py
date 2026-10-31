"""Run all 250 frozen observations on Jev or GPT; never load grading references."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import boto3
import httpx
from ablation_protocol import selected_payload
from api_ablation_protocol import (
    GPT_MODEL,
    JEV_URL,
    decode_gpt,
    decode_jev,
    gpt_request,
    jev_request,
)
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from run_resident import save, sha, stamp, wire


def invoke(provider, client, payload, expected_model=None):
    request = gpt_request(payload) if provider == "gpt" else jev_request(payload)
    stage = {"payload": payload, "input_sha256": sha(payload),
             "transport_request": request, "transport_sha256": sha(request), "started_at": stamp()}
    started = time.perf_counter()
    try:
        if provider == "gpt":
            response = client.converse(**request)
            stage.update(response=response, http_status=response["ResponseMetadata"]["HTTPStatusCode"],
                         request_id=response["ResponseMetadata"]["RequestId"], status="ok",
                         model_id=GPT_MODEL, model_identity_source="request modelId; verified Bedrock inference profile",
                         server_ms=response.get("metrics", {}).get("latencyMs"))
        else:
            reply = client.post(JEV_URL, json=request)
            stage.update(http_status=reply.status_code, response_text=reply.text,
                         request_id=reply.headers.get("x-request-id"),
                         status="ok" if reply.status_code == 200 else "http_error")
            try:
                response = reply.json()
            except ValueError:
                if stage["status"] == "http_error":
                    stage["client_ms"] = round((time.perf_counter() - started) * 1000, 3)
                    return stage
                raise
            stage["response"] = response
            stage["model_id"] = response.get("model")
            stage["server_ms"] = response.get("latency_ms")
        stage["client_ms"] = round((time.perf_counter() - started) * 1000, 3)
        if stage["status"] == "ok":
            stage["choices"] = (
                decode_gpt(response, payload) if provider == "gpt"
                else decode_jev(response, payload, expected_model)
            )
    except (httpx.HTTPError, BotoCoreError, ClientError) as error:
        stage.update(status="transport_error", error_type=type(error).__name__)
        if isinstance(error, ClientError):
            stage["provider_error"] = error.response
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        stage.update(status="format_error", error=str(error))
    stage.setdefault("client_ms", round((time.perf_counter() - started) * 1000, 3))
    return stage


def observe(experiment, provider, client, expected_model=None):
    row = {k: experiment[k] for k in ("case_id", "dataset", "variant", "arm")}
    row.update(provider=provider, started_at=stamp(), stages=[], status="ok")
    payload = experiment["first_payload"]
    while payload is not None:
        stage = invoke(provider, client, payload, expected_model)
        stage["stage"] = "gate" if experiment["arm"] == "two_stage" and not row["stages"] else "value"
        row["stages"].append(stage)
        if stage["status"] != "ok":
            row["status"] = stage["status"]
            break
        if stage["stage"] == "gate":
            row["gate_selected_keys"] = [k for k, v in stage["choices"].items() if v == "apply"]
            payload = selected_payload(experiment["value_payload"], stage["choices"])
        else:
            payload = None
    row["client_ms"] = sum(s["client_ms"] for s in row["stages"])
    times = [s.get("server_ms") for s in row["stages"]]
    row["server_ms"] = sum(times) if all(isinstance(v, (int, float)) for v in times) else None
    return row


def run(args):
    plan = json.loads((args.run / "plan.json").read_text())
    experiments = json.loads((args.run / "experiments.json").read_text())
    if sha(experiments) != plan["experiments_sha256"]:
        raise ValueError("Frozen experiments changed")
    for name, checksum in plan["source_sha256"].items():
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Source changed: " + name)
    if args.phase == "probe":
        experiments = [e for e in experiments if e["case_id"] == "S01" and e["variant"] == "original"]
    output = args.run / args.provider
    output.mkdir(exist_ok=True)
    path = output / (args.phase + "_receipts.jsonl")
    if path.exists():
        raise FileExistsError("Refusing to overwrite saved observations")
    expected_model = None
    if args.phase == "formal":
        probe = json.loads((output / "probe_run.json").read_text())
        if probe["status"] != "complete" or probe["errors"]:
            raise ValueError("Successful protocol preflight required")
        if args.provider == "jev":
            if len(probe["observed_models"]) != 1:
                raise ValueError("Cannot pin a unique Jev version")
            expected_model = probe["observed_models"][0]
    config = Config(connect_timeout=10, read_timeout=180, retries={"total_max_attempts": 1})
    if args.provider == "gpt":
        client = boto3.client("bedrock-runtime", region_name=plan["region"], config=config)
    else:
        secret = boto3.client("secretsmanager", region_name=plan["region"], config=config).get_secret_value(
            SecretId=plan["jev_secret_arn"],
        )["SecretString"].strip()
        client = httpx.Client(headers={"Authorization": "Bearer " + secret},
                              timeout=httpx.Timeout(180, connect=10), trust_env=False,
                              follow_redirects=False)
    metadata = {
        "provider": args.provider, "phase": args.phase, "started_at": stamp(),
        "status": "running", "planned_observations": len(experiments), "actual_observations": 0,
        "actual_calls": 0, "errors": 0, "automatic_retries": 0, "concurrency_per_provider": 1,
        "expected_model": GPT_MODEL if args.provider == "gpt" else expected_model,
        "observed_models": [], "experiments_sha256": plan["experiments_sha256"],
        "plan_file_sha256": hashlib.sha256((args.run / "plan.json").read_bytes()).hexdigest(),
    }
    save(output / (args.phase + "_run.json"), metadata)
    try:
        with path.open("x") as stream:
            for experiment in experiments:
                row = observe(experiment, args.provider, client, expected_model)
                stream.write(wire(row) + "\n")
                stream.flush()
                metadata["actual_observations"] += 1
                metadata["actual_calls"] += len(row["stages"])
                metadata["errors"] += row["status"] != "ok"
                metadata["last_case"] = row["case_id"]
                metadata["last_arm"] = row["arm"]
                metadata["last_variant"] = row["variant"]
                for stage in row["stages"]:
                    model = stage.get("model_id")
                    if model and model not in metadata["observed_models"]:
                        metadata["observed_models"].append(model)
                save(output / (args.phase + "_run.json"), metadata)
                if metadata["actual_observations"] % 10 == 0 or row["status"] != "ok":
                    print(wire({k: metadata[k] for k in (
                        "provider", "actual_observations", "actual_calls", "errors", "last_case", "last_arm",
                    )}), flush=True)
        metadata.update(status="complete", finished_at=stamp())
    finally:
        client.close()
        save(output / (args.phase + "_run.json"), metadata)
    print(wire(metadata), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--provider", choices=["jev", "gpt"], required=True)
    parser.add_argument("--phase", choices=["probe", "formal"], required=True)
    run(parser.parse_args())
