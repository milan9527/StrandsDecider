"""Call the deployed Decider, recording raw responses without offline references."""

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from prepare import save, sha, wire


def stamp():
    return datetime.now(UTC).isoformat()


def run(args):
    plan = json.loads((args.run / "plan.json").read_text())
    requests = json.loads((args.run / "requests.json").read_text())
    if sha(requests) != plan["requests_sha256"]:
        raise ValueError("Frozen requests have changed")
    for request in requests:
        if sha(request["payload"]) != request["input_sha256"]:
            raise ValueError("Request hash mismatch")
    credential = json.loads(args.credentials.read_text()) if args.credentials else {}
    key = os.environ.get("DECIDER_VLLM_API_KEY") or credential["api_key"]
    endpoint = args.endpoint or credential.get("endpoint")
    if not endpoint:
        raise ValueError("An endpoint is required")
    endpoint = endpoint.rstrip("/")
    if args.probe:
        # Plumbing/context validation is retained separately, not scored.
        requests = requests[:1]
        prefix = "probe"
    else:
        prefix = "formal"
    metadata = {
        "started_at": stamp(), "status": "running", "endpoint": endpoint,
        "requests_sha256": plan["requests_sha256"], "planned_calls": len(requests),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "automatic_retries": 0,
    }
    output = args.run / f"{prefix}_receipts.jsonl"
    with output.open("x") as stream, httpx.Client(
        base_url=endpoint, headers={"Authorization": f"Bearer {key}"},
        timeout=60, trust_env=False,
    ) as client:
        for path, name in [("/health", "health_before"), ("/v1/models", "models")]:
            response = client.get(path)
            response.raise_for_status()
            data = response.json()
            save(args.run / f"{prefix}_{name}.json", data)
            if path == "/health" and (
                data.get("status") != "ok"
                or data.get("model") != "strands-decider-2B-hobson-v19-vllm"
            ):
                raise RuntimeError("Unexpected model or unhealthy service")
        save(args.run / f"{prefix}_run.json", metadata)
        try:
            for request in requests:
                receipt = {
                    "case_id": request["case_id"], "variant": request["variant"],
                    "input_sha256": request["input_sha256"], "started_at": stamp(),
                }
                start = time.perf_counter()
                try:
                    response = client.post("/v1/systemone", json=request["payload"])
                    receipt.update(
                        client_ms=round((time.perf_counter() - start) * 1000, 3),
                        http_status=response.status_code,
                        request_id=response.headers.get("x-request-id"),
                        response_text=response.text,
                    )
                    try:
                        receipt["response"] = response.json()
                    except ValueError:
                        pass
                    receipt["status"] = "ok" if response.status_code == 200 else "http_error"
                except httpx.HTTPError as error:
                    receipt.update(
                        client_ms=round((time.perf_counter() - start) * 1000, 3),
                        status="transport_error", error=str(error),
                    )
                stream.write(wire(receipt) + "\n")
                stream.flush()
                print(wire({
                    "case": request["case_id"], "variant": request["variant"],
                    "status": receipt["status"], "client_ms": receipt["client_ms"],
                    "server_ms": receipt.get("response", {}).get("latency_ms"),
                    "error": receipt.get("response", {}).get("detail"),
                }), flush=True)
            metadata.update(status="complete", finished_at=stamp(), actual_calls=len(requests))
        finally:
            save(args.run / f"{prefix}_run.json", metadata)
        response = client.get("/health")
        save(args.run / f"{prefix}_health_after.json", {
            "http_status": response.status_code, "body": response.json(),
        })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    run(args)
