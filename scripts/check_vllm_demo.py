"""Verify every demo Decider path against the live shared vLLM service."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

MODEL = "strands-decider-2B-hobson-v19-vllm"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path; previous evidence is never overwritten.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "purpose": "Integration verification; not a comparative performance benchmark",
        "url": args.url,
        "records": [],
    }

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    with httpx.Client(
        base_url=args.url.rstrip("/"),
        headers={"X-Decider-Client": "web"},
        timeout=65,
        trust_env=False,
    ) as client:
        response = client.post("/api/auth/login", json=json.loads(args.credentials.read_text()))
        response.raise_for_status()

        def get(path):
            response = client.get(path)
            response.raise_for_status()
            return response.json()

        def post(module, path, payload):
            started = perf_counter()
            response = client.post(path, json=payload)
            record = {
                "module": module, "path": path, "request": payload,
                "http_status": response.status_code,
                "client_ms": round((perf_counter() - started) * 1000, 3),
                "response": response.json(),
            }
            report["records"].append(record)
            save()
            response.raise_for_status()
            data = record["response"]
            decision = data.get("decision") if path.endswith("/tick") else data
            if decision is not None:
                assert decision["model"] == MODEL, (module, decision.get("model"))
            return data

        report["health"] = get("/api/health")
        report["gpu"] = get("/api/gpu")
        assert report["health"]["connected"]
        assert report["health"]["upstream"]["engine"] == "vllm"
        assert report["health"]["upstream"]["model"] == MODEL
        assert report["gpu"]["provider"] == "vllm" and not report["gpu"]["can_manage"]
        save()
        examples = get("/api/examples")
        example = next(row for row in examples if row["id"] == "support")
        workbench = {
            "mode": "live", "state": example["state"], "questions": example["questions"],
        }
        for measure in (False, True):
            data = post("workbench", "/api/decide", {
                **workbench, "measure_decisions": measure,
            })
            assert {a["type"] for a in data["answers"].values()} == {"choice", "noul", "score"}
        post("guard", "/api/guard", {
            "mode": "live", "message": "What is the weather in Seattle?",
            "location": "Seattle", "threshold": 0.45, "measure_decisions": True,
        })
        catalog = get("/api/crypto/catalog")
        for case in catalog["cases"]:
            for profile in ("baseline", "optimized"):
                for stage in catalog["stages"]:
                    post("payment", "/api/crypto/decision", {
                        "snapshot": case["snapshot"], "stage": stage["id"],
                        "provider": "decider", "mode": "live", "input_profile": profile,
                    })
            state = {"snapshot": case["snapshot"]}
            for _ in range(34):
                data = post("closed_loop", "/api/crypto/loop/tick", {
                    "state": state, "provider": "decider", "mode": "live", "auto_events": True,
                })
                state = data["state"]
                if state["status"] in ("complete", "handoff"):
                    break
            else:
                raise AssertionError(f"Loop did not stop: {case['id']}")
            report.setdefault("loop_outcomes", {})[case["id"]] = {
                "status": state["status"], "reason": state["reason"],
                "decisions": state["decisions"], "ticks": state["ticks"],
            }
        catalog = get("/api/routing/catalog")
        for case in catalog["cases"]:
            payload = {
                "task": {"text": case["task"]}, "provider": "decider", "mode": "live",
                "strategy": "original", "catalog_version": catalog["version"],
                "ranking_version": catalog["rankings"]["version"],
            }
            flow = post("routing", "/api/routing/decision", {**payload, "stage": "workflow"})
            post("routing", "/api/routing/decision", {
                **payload, "stage": "model", "workflow": flow["choice"],
            })
        # Keep result recording on the main thread; the two HTTP calls overlap.
        started = perf_counter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(
                lambda _: client.post("/api/decide", json=workbench), range(2),
            ))
        report["concurrent_smoke"] = {
            "requests": 2, "elapsed_ms": round((perf_counter() - started) * 1000, 3),
            "responses": [{"http_status": r.status_code, "result": r.json()} for r in replies],
        }
        for response in replies:
            response.raise_for_status()
            assert response.json()["model"] == MODEL
    report["passed"] = True
    report["finished_at"] = datetime.now(UTC).isoformat()
    save()
    print(json.dumps({
        "passed": True, "records": len(report["records"]), "model": MODEL,
        "loop_outcomes": report["loop_outcomes"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
