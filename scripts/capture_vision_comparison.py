"""Capture all 12 image cases through the deployed API, preserving warmup and failures."""

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

PROVIDERS = ("decider", "jev", "bedrock")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; keep previous measurements and choose a new path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    credentials = json.loads(args.credentials.read_text())
    report = {"started_at": datetime.now(UTC).isoformat(), "url": args.url,
              "method": "12 presets; one warmup per provider; concurrent providers, sequential cases",
              "warmup": [], "results": []}
    with httpx.Client(base_url=args.url, headers={"X-Decider-Client": "web", "Origin": args.url},
                      timeout=60, follow_redirects=False) as client:
        client.post("/api/auth/login", json=credentials).raise_for_status()
        catalog = client.get("/api/vision/catalog")
        catalog.raise_for_status()
        cases = catalog.json()["cases"]

        def call(case, provider):
            started = perf_counter()
            body = {"provider": provider, "mode": "live", "case_id": case["id"], "variant": "original"}
            try:
                response = client.post("/api/vision/decide", json=body)
                data = response.json()
                return {"case_id": case["id"], "group": case["group"], "provider": provider,
                        "status": response.status_code, "client_ms": (perf_counter() - started) * 1000,
                        "response": data}
            except (httpx.HTTPError, ValueError) as exc:
                return {"case_id": case["id"], "group": case["group"], "provider": provider,
                        "status": "transport_error", "error": type(exc).__name__,
                        "client_ms": (perf_counter() - started) * 1000}

        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                report["warmup"] = list(pool.map(lambda p: call(cases[0], p), PROVIDERS))
                for case in cases:
                    rows = list(pool.map(lambda p, current=case: call(current, p), PROVIDERS))
                    report["results"].extend(rows)
                    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                    print(json.dumps({"case": case["id"], "statuses": [r["status"] for r in rows]}), flush=True)
        finally:
            client.post("/api/auth/logout")
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["summary"] = {}
    for provider in PROVIDERS:
        rows = [r for r in report["results"] if r["provider"] == provider]
        good = [r for r in rows if r["status"] == 200]
        correct = total = 0
        groups = {}
        for row in good:
            data = row["response"]
            group = groups.setdefault(row["group"], {"correct": 0, "questions": 0, "backend_ms": []})
            group["backend_ms"].append(data["backend_total_ms"])
            for key, answer in data["answers"].items():
                actual = answer["choice"] if answer["type"] == "choice" else answer.get("value", answer.get("noul", 0) >= .5)
                matched = actual == data["expected"][key]
                correct += matched
                total += 1
                group["correct"] += matched
                group["questions"] += 1
        for group in groups.values():
            group["mean_backend_ms"] = statistics.mean(group.pop("backend_ms"))
        latencies = [r["response"]["backend_total_ms"] for r in good]
        report["summary"][provider] = {
            "models": sorted({r["response"]["model"] for r in good}),
            "success": len(good), "failed": len(rows) - len(good), "correct": correct,
            "answered_questions": total, "planned_questions": 28,
            "mean_backend_ms": statistics.mean(latencies) if latencies else None,
            "median_backend_ms": statistics.median(latencies) if latencies else None,
            "groups": groups,
        }
    for case in cases:
        rows = [r for r in report["results"] if r["case_id"] == case["id"] and r["status"] == 200]
        assert len({r["response"]["input_fingerprint"] for r in rows}) <= 1
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
