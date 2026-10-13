"""Bounded live load test of the deployed payment decision API, with saved evidence."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import random
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("decider", "jev", "bedrock")
STAGES = ("intake", "verify", "approve", "execute", "close")


def now():
    return datetime.now(UTC).isoformat()


def percentile(values, quantile):
    """Nearest-rank empirical percentile; no interpolation or fitted distribution."""
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)] if values else None


def distribution(values):
    if not values:
        return None
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "min": min(values),
        "max": max(values),
    }


def summarize(rows, elapsed_seconds):
    success = [r for r in rows if r["success"]]
    timing = [r["result"]["timings"] for r in success]
    return {
        "attempts": len(rows),
        "successes": len(success),
        "failures": len(rows) - len(success),
        "status_counts": dict(Counter(str(r["status"]) for r in rows)),
        "success_rate": len(success) / len(rows),
        "wall_seconds": elapsed_seconds,
        "successful_requests_per_second": len(success) / elapsed_seconds,
        "all_attempts_per_second": len(rows) / elapsed_seconds,
        "client_latency_ms_all": distribution([r["client_ms"] for r in rows]),
        "client_latency_ms_success": distribution([r["client_ms"] for r in success]),
        "client_latency_ms_failure": distribution(
            [r["client_ms"] for r in rows if not r["success"]]
        ),
        "backend_total_ms": distribution([t["backend_total_ms"] for t in timing]),
        "processing_ms": distribution([t["processing_ms"] for t in timing]),
        "backend_wait_and_preamble_ms": distribution(
            [max(0, t["backend_total_ms"] - t["processing_ms"]) for t in timing]
        ),
        "model_reported_ms": distribution(
            [t["model_reported_ms"] for t in timing if t.get("model_reported_ms") is not None]
        ),
        "reference_matches": sum(r["result"]["matches_reference"] for r in success),
        "models": dict(Counter(r["result"]["model"] for r in success)),
    }


async def main(args):
    if args.output.exists():
        raise SystemExit("Output exists; choose a new output directory to preserve prior evidence.")
    args.output.mkdir(parents=True)
    source = json.loads(args.source.read_text())
    corpus = []
    for case, data in source["cases"].items():
        for stage in STAGES:
            result = data["results"]["decider"][stage]
            corpus.append(
                {
                    "case": case,
                    "stage": stage,
                    "snapshot": data["snapshot"],
                    "input_hash": result["input_hash"],
                    "model_input": result["model_input"],
                }
            )
    assert len(corpus) == 20 and args.requests % 20 == 0
    assert args.requests >= max(args.levels)
    rng = random.Random(args.seed)
    order = []
    for _ in range(args.requests // 20):
        cycle = list(range(20))
        rng.shuffle(cycle)
        order.extend(cycle)
    (args.output / "corpus.json").write_text(
        json.dumps(
            {
                "source": str(args.source.relative_to(ROOT)),
                "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
                "tasks": corpus,
                "dispatch_order": order,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    metadata = {
        "started_at": now(),
        "url": args.url,
        "endpoint": "/api/crypto/decision",
        "design": {
            "providers": list(PROVIDERS),
            "client_concurrency_levels": args.levels,
            "requests_per_cell": args.requests,
            "distinct_inputs": 20,
            "repetitions_per_input_per_cell": args.requests // 20,
            "seed": args.seed,
            "input_profile": "optimized",
            "load_model": "Closed loop: C asynchronous workers, immediate replacement after completion, no think time. Providers tested separately; provider order rotates between levels.",
            "warmup": "All 20 tasks once per provider before testing; before each cell, 2 requests per supported model slot (1 Decider slot, 2 Jev/GPT slots). All warmups excluded.",
            "retries": "No load-client retries. Existing backend connection policy unchanged.",
            "transport": "HTTPS/HTTP1.1 via CloudFront, persistent httpx client, connection pool >= max concurrency; includes authentication, network, queue and processing.",
            "safety_bound": "At most 80 requests per cell by default; stop higher levels for a provider if cell failure rate reaches 25%. No execution, GPU lifecycle or deployment API calls.",
            "quantiles": "Nearest rank on successful client latencies; all-attempt and failed latency distributions also retained. No P99 claim with n=80.",
        },
        "runner": {
            "platform": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
        },
        "cells": [],
        "skipped": [],
    }
    manifest_path = args.output / "manifest.json"

    def save():
        manifest_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")

    save()
    credentials = json.loads(args.credentials.read_text())
    headers = {"X-Decider-Client": "web", "Origin": args.url, "Cache-Control": "no-store"}
    limits = httpx.Limits(
        max_connections=max(args.levels) + 4, max_keepalive_connections=max(args.levels) + 4
    )
    records_file = (args.output / "requests.jsonl").open("w")
    warm_file = (args.output / "warmups.jsonl").open("w")
    async with httpx.AsyncClient(
        base_url=args.url,
        headers=headers,
        limits=limits,
        timeout=httpx.Timeout(75, connect=5, pool=5),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = await client.post("/api/auth/login", json=credentials)
        assert response.status_code == 200, f"Login failed: HTTP {response.status_code}"
        response = await client.get("/api/gpu")
        response.raise_for_status()
        gpu = response.json()
        assert gpu["phase"] == "ready", "Existing GPU must be ready; benchmark never starts it."
        metadata["gpu"] = {
            k: gpu.get(k) for k in ("phase", "provider", "instance_type", "idle_auto_stop")
        }
        health = await client.get("/api/health")
        health.raise_for_status()
        assert health.json()["connected"]
        save()

        async def invoke(provider, task_index, index, concurrency, phase):
            task = corpus[task_index]
            row = {
                "phase": phase,
                "provider": provider,
                "concurrency": concurrency,
                "index": index,
                "task_index": task_index,
                "case": task["case"],
                "stage": task["stage"],
                "started_at": now(),
            }
            started = perf_counter()
            try:
                response = await client.post(
                    "/api/crypto/decision",
                    json={
                        "snapshot": task["snapshot"],
                        "stage": task["stage"],
                        "provider": provider,
                        "mode": "live",
                        "input_profile": "optimized",
                    },
                )
                row["status"] = response.status_code
                try:
                    data = response.json()
                except ValueError:
                    data = {"detail": "Non-JSON HTTP response"}
                row["client_ms"] = (perf_counter() - started) * 1000
                row["success"] = (
                    response.status_code == 200
                    and data.get("source") == "live"
                    and data.get("input_hash") == task["input_hash"]
                    and data.get("model_input") == task["model_input"]
                    and isinstance(data.get("timings", {}).get("backend_total_ms"), (int, float))
                )
                row["input_verified"] = data.get("model_input") == task["model_input"]
                if row["success"]:
                    row["result"] = {
                        key: data.get(key)
                        for key in (
                            "model",
                            "choice",
                            "label",
                            "confidence",
                            "probabilities",
                            "input_hash",
                            "reference_choice",
                            "matches_reference",
                            "timings",
                            "usage",
                        )
                    }
                else:
                    row["error"] = str(
                        data.get("detail", "Invalid response or changed business input")
                    )[:500]
                    row["retry_after"] = response.headers.get("retry-after")
            except httpx.HTTPError as exc:
                row.update(
                    status="transport_error",
                    success=False,
                    error=type(exc).__name__,
                    client_ms=(perf_counter() - started) * 1000,
                )
            row["finished_at"] = now()
            target = warm_file if phase != "measured" else records_file
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
            target.flush()
            return row

        # Prime all request shapes; any failure is recorded and ends the run.
        for provider in PROVIDERS:
            for index in range(20):
                row = await invoke(provider, index, index, 1, "initial_warmup")
                if not row["success"]:
                    raise RuntimeError(f"{provider} initial warmup failed: {row['status']}")
            print(f"Primed 20 tasks: {provider}", flush=True)

        stopped = set()
        for level_index, concurrency in enumerate(args.levels):
            providers = PROVIDERS[level_index % 3 :] + PROVIDERS[: level_index % 3]
            for provider in providers:
                if provider in stopped:
                    metadata["skipped"].append({"provider": provider, "concurrency": concurrency})
                    save()
                    continue
                slots = 1 if provider == "decider" else 2
                for repeat in range(2):
                    warm = await asyncio.gather(
                        *(
                            invoke(provider, slot, repeat * slots + slot, slots, "cell_warmup")
                            for slot in range(slots)
                        )
                    )
                    if not all(r["success"] for r in warm):
                        raise RuntimeError(f"{provider} cell warmup failed; records preserved.")
                print(
                    f"Measuring {provider}: concurrency={concurrency}, n={args.requests}",
                    flush=True,
                )
                counter = iter(enumerate(order))
                rows = []
                active = 0
                max_active = 0
                cell_start = now()
                elapsed_start = perf_counter()

                async def worker(
                    counter=counter, provider=provider, concurrency=concurrency, rows=rows
                ):
                    nonlocal active, max_active
                    for index, task_index in counter:
                        active += 1
                        max_active = max(max_active, active)
                        try:
                            row = await invoke(provider, task_index, index, concurrency, "measured")
                            rows.append(row)
                        finally:
                            active -= 1

                await asyncio.gather(*(worker() for _ in range(concurrency)))
                elapsed_seconds = perf_counter() - elapsed_start
                summary = summarize(rows, elapsed_seconds)
                cell = {
                    "provider": provider,
                    "concurrency": concurrency,
                    "started_at": cell_start,
                    "finished_at": now(),
                    "max_observed_inflight": max_active,
                    **summary,
                }
                metadata["cells"].append(cell)
                save()
                latency = summary["client_latency_ms_success"]
                print(
                    f"Result {provider} C={concurrency}: {summary['successes']}/{len(rows)}; "
                    f"{summary['successful_requests_per_second']:.2f} req/s; "
                    f"p50={latency['p50'] if latency else None} ms; "
                    f"p95={latency['p95'] if latency else None} ms",
                    flush=True,
                )
                if summary["failures"] / len(rows) >= 0.25:
                    stopped.add(provider)
        metadata["finished_at"] = now()
        metadata["status"] = "complete"
        save()
        # Revoke only the benchmark's own session.
        await client.post("/api/auth/logout")
    records_file.close()
    warm_file.close()
    print(f"Saved {len(metadata['cells'])} cells to {args.output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://d3i7ogfx5ml7dc.cloudfront.net")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "docs/presentations/v8/live-observations.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8, 16, 32])
    parser.add_argument("--requests", type=int, default=80)
    parser.add_argument("--seed", type=int, default=20261013)
    args = parser.parse_args()
    args.source = args.source.resolve()
    if not args.levels or min(args.levels) < 1 or max(args.levels) > 32:
        raise SystemExit("Supported client concurrency is 1..32.")
    asyncio.run(main(args))
