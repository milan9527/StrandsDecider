"""Add Jev/GPT to the frozen candidate protocol; acceptance is only the spec's 20 cases."""

import argparse
import copy
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import boto3
import httpx
from api_ablation_protocol import GPT_MODEL, GPT_SYSTEM, JEV_MODEL
from botocore.config import Config
from prepare import SPEC, payload, read_spec
from resume_api_capture import encode_binary
from run_api_ablation import invoke
from run_candidate_benchmark import sha, stamp

HERE = Path(__file__).parent
SOURCES = (
    "run_spec_cloud.py", "api_ablation_protocol.py", "run_api_ablation.py",
    "resume_api_capture.py", "run_ablation.py", "ablation_protocol.py",
    "run_resident.py", "run_candidate_benchmark.py", "prepare.py",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False, default=encode_binary) + "\n")


def prepare(root, parent, api_parent):
    capabilities, references = read_spec()
    cases = json.loads((parent / "cases.json").read_text())
    parent_refs = {r["id"]: r for r in json.loads((parent / "references.json").read_text())}
    for ref in references:
        assert all(parent_refs[ref["id"]][key] == value for key, value in ref.items())
        for order in ("original", "reversed"):
            case = next(c for c in cases if c["case_id"] == ref["id"] and c["order"] == order)
            assert sha(case["payload"]) == sha(payload(ref["query"], capabilities, order == "reversed"))
    assert len(cases) == 156
    api = json.loads((api_parent / "plan.json").read_text())
    root.mkdir(parents=True, exist_ok=False)
    (root / "sources").mkdir()
    for name in SOURCES:
        (root / "sources" / name).write_bytes((HERE / name).read_bytes())
    for name in ("cases.json", "references.json", "command_set.json", "models.json"):
        (root / name).write_bytes((parent / name).read_bytes())
    (root / "spec.md").write_bytes(SPEC.read_bytes())
    save(root / "spec_references.json", references)
    save(root / "plan.json", {
        "prepared_at": stamp(), "parent_run": parent.name,
        "acceptance": "Only original-order S01-S10 and M01-M10 from spec.md; 20 cases, 40 expected pairs.",
        "supplementary": "Reversed options and 116 non-spec requests excluded from primary score. "
                         "Retain the parent's entire 156-request sequence before timing so "
                         "each provider has the same task and warmup history.",
        "schedule": "3 S03 full warmups; 156 frozen quality requests; 30 single-field warmups; "
                    "3 rounds alternating single_key/serial30/full30 and full30/serial30/single_key.",
        "providers": ["jev", "gpt"], "calls_per_provider": 285,
        "formal_per_provider": 252, "warmups_per_provider": 33,
        "primary_requests_per_provider": 20, "timing_case": "S03", "timing_repetitions": 3,
        "outer_concurrency": 1, "automatic_retries": 0, "output_repair": False,
        "references_sent_to_models": False,
        "serial30_artifact_operations_inside_block": 0,
        "region": api["region"], "jev_secret_arn": api["jev_secret_arn"],
        "jev_request_model": JEV_MODEL,
        "jev_response_version": "Pin first successful warmup; enforce on every subsequent response.",
        "gpt_model": GPT_MODEL, "gpt_effort": "low", "gpt_system": GPT_SYSTEM,
        "gpt_max_output_tokens": 8192,
        "transport": "Jev native HTTPS/httpx; GPT Bedrock Converse/boto3; persistent clients.",
        "client_host": platform.node(),
        "latency_scope": "Client request/response duration including provider network and SDK. "
                         "L4 parent used loopback from the GPU host. No network-time subtraction.",
        "cache_policy": "No explicit provider cache controls; retain native cache/usage evidence.",
        "input_files_sha256": {name: digest(root / name) for name in (
            "cases.json", "references.json", "command_set.json", "models.json", "spec.md",
            "spec_references.json")},
        "source_sha256": {name: digest(root / "sources" / name) for name in SOURCES},
        "parent_evidence_sha256": {str(p.relative_to(parent)): digest(p) for p in [
            parent / "plan.json", parent / "source-transfer.json", parent / "audit.json",
            *sorted((parent / "results").glob("*/receipts.jsonl")),
            *sorted((parent / "results").glob("*/run.json")),
        ]},
    })
    print(json.dumps({"prepared": str(root), "primary_cases": 20,
                      "new_calls": 570, "new_warmups": 66}), flush=True)


def run(root):
    plan = json.loads((root / "plan.json").read_text())
    # Only inference inputs and code are read here; grading references remain offline.
    assert digest(root / "cases.json") == plan["input_files_sha256"]["cases.json"]
    for name, expected in plan["source_sha256"].items():
        assert digest(HERE / name) == expected, name
    cases = json.loads((root / "cases.json").read_text())
    s03 = next(c for c in cases if c["case_id"] == "S03" and c["order"] == "original")
    output = root / "results"
    output.mkdir(exist_ok=False)
    config = Config(connect_timeout=10, read_timeout=180, retries={"total_max_attempts": 1})
    profile = boto3.client("bedrock", region_name=plan["region"], config=config).get_inference_profile(
        inferenceProfileIdentifier=GPT_MODEL)
    save(root / "bedrock_profile.json", json.loads(json.dumps(profile, default=str)))
    assert profile["status"] == "ACTIVE"
    save(root / "client_environment.json", {
        "recorded_at": stamp(), "python": sys.version, "platform": platform.platform(),
        "hostname": platform.node(), "boto3": boto3.__version__, "httpx": httpx.__version__,
    })
    for provider in plan["providers"]:
        folder = output / provider
        folder.mkdir()
        meta = {
            "provider": provider, "started_at": stamp(), "status": "running",
            "calls": 0, "errors": 0, "external_concurrency": 1, "automatic_retries": 0,
            "serial30_blocks": [], "plan_sha256": digest(root / "plan.json"),
            "expected_model": GPT_MODEL if provider == "gpt" else None,
        }
        save(folder / "run.json", meta)
        if provider == "jev":
            secret = boto3.client("secretsmanager", region_name=plan["region"], config=config
                                  ).get_secret_value(SecretId=plan["jev_secret_arn"])["SecretString"].strip()
            client = httpx.Client(headers={"Authorization": "Bearer " + secret},
                                  timeout=httpx.Timeout(180, connect=10),
                                  trust_env=False, follow_redirects=False)
            del secret
        else:
            client = boto3.client("bedrock-runtime", region_name=plan["region"], config=config)

        def observe(case, kind, repetition=0, key=None, *, provider=provider, client=client, meta=meta):
            task = copy.deepcopy(case["payload"])
            if key is not None:
                task["questions"] = {key: task["questions"][key]}
            row = {k: case[k] for k in ("case_id", "dataset", "order", "language")}
            row.update(provider=provider, kind=kind, repetition=repetition)
            row.update(invoke(provider, client, task, meta["expected_model"]))
            row["commands"] = [{"cmdKey": k, "cmdValue": v}
                               for k, v in row.get("choices", {}).items() if v != "omit"]
            row["finished_at"] = stamp()
            if provider == "jev" and meta["expected_model"] is None and row["status"] == "ok":
                meta["expected_model"] = row["model_id"]
            return row

        try:
            with (folder / "receipts.jsonl").open("x") as stream:
                def record(rows, *, meta=meta, folder=folder, provider=provider):
                    for row in rows:
                        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"),
                                                allow_nan=False, default=encode_binary) + "\n")
                        meta["calls"] += 1
                        meta["errors"] += row["status"] != "ok"
                        meta["last"] = {k: row[k] for k in ("case_id", "order", "kind", "repetition")}
                    stream.flush()
                    save(folder / "run.json", meta)
                    print(json.dumps({"provider": provider, "calls": meta["calls"],
                                      "errors": meta["errors"], "last": meta["last"]}), flush=True)

                for repetition in range(3):
                    row = observe(s03, "warmup_full30", repetition)
                    record([row])
                    assert row["status"] == "ok", "Warmup failed; evidence saved, no retry."
                failures = 0
                for case in cases:
                    row = observe(case, "quality")
                    record([row])
                    failures = failures + 1 if row["status"] != "ok" else 0
                    assert failures < 3, "Three consecutive failures; evidence saved."
                for key in s03["payload"]["questions"]:
                    row = observe(s03, "warmup_single", key=key)
                    record([row])
                    assert row["status"] == "ok", "Single-field warmup failed."
                for repetition in range(3):
                    order = ("single_key", "serial30", "full30") if repetition % 2 == 0 else (
                        "full30", "serial30", "single_key")
                    for kind in order:
                        if kind == "serial30":
                            started_at, started = stamp(), time.perf_counter()
                            rows = [observe(s03, kind, repetition, key)
                                    for key in s03["payload"]["questions"]]
                            elapsed = (time.perf_counter() - started) * 1000
                            meta["serial30_blocks"].append({
                                "repetition": repetition, "started_at": started_at, "finished_at": stamp(),
                                "wall_ms": elapsed, "http_sum_ms": sum(r["client_ms"] for r in rows),
                                "artifact_operations_inside_block": 0,
                            })
                        else:
                            rows = [observe(s03, kind, repetition,
                                            "t_temp" if kind == "single_key" else None)]
                        record(rows)
                        assert all(r["status"] == "ok" for r in rows), "Timing failure; no replay."
                assert meta["calls"] == plan["calls_per_provider"]
                meta["status"] = "complete" if not meta["errors"] else "complete_with_errors"
        except BaseException as error:
            meta.update(status="failed", error_type=type(error).__name__, error=str(error))
            raise
        finally:
            client.close()
            meta["finished_at"] = stamp()
            save(folder / "run.json", meta)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--parent", type=Path, default=HERE / "runs/2026-10-30-candidates-l4-v1")
    parser.add_argument("--api-parent", type=Path, default=HERE / "runs/2026-10-30-api-ablation-v1")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.run, args.parent, args.api_parent)
    else:
        run(args.run)
