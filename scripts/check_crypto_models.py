"""Record real paired decisions and exercise guarded sandbox workflows."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".deployment/crypto-models-live.json"))
    args = parser.parse_args()
    observed = []
    with httpx.Client(base_url=args.url, headers={"X-Decider-Client": "web"}, timeout=65) as client:

        def request(path, body=None):
            response = client.get(path) if body is None else client.post(path, json=body)
            response.raise_for_status()
            return response.json()

        request("/api/auth/login", json.loads(args.credentials.read_text()))
        try:
            health = request("/api/health")
            assert health["connected"] and health["upstream"]["device"] == "cuda"
            catalog = request("/api/crypto/catalog")
            assert catalog["bedrock_models"][0]["id"] == "us.openai.gpt-6.1-sol"
            with ThreadPoolExecutor(max_workers=2) as pool:
                for case in catalog["cases"]:
                    rows = []
                    for stage in catalog["stages"]:
                        body = {"snapshot": case["snapshot"], "stage": stage["id"], "mode": "live"}
                        futures = {
                            p: pool.submit(request, "/api/crypto/decision", {**body, "provider": p})
                            for p in ("decider", "bedrock")
                        }
                        row = {"stage": stage["id"], **{p: f.result() for p, f in futures.items()}}
                        a, b = row["decider"], row["bedrock"]
                        assert a["source"] == b["source"] == "live"
                        assert a["input_hash"] == b["input_hash"]
                        assert a["model"] == "strands-decider-2B-hobson-v19"
                        assert b["model"] == "us.openai.gpt-6.1-sol"
                        assert a["timings"]["backend_total_ms"] > 0
                        assert b["timings"]["backend_total_ms"] > 0
                        assert b["usage"]["input_tokens"] > 0
                        rows.append(row)
                    workflows = {}
                    for provider in ("decider", "bedrock"):
                        state = case["snapshot"]
                        actions = []
                        for row in rows:
                            result = row[provider]
                            applied = request(
                                "/api/crypto/apply",
                                {
                                    "snapshot": state,
                                    "stage": row["stage"],
                                    "choice": result["choice"],
                                },
                            )
                            assert applied["requested_action"] == result["choice"]
                            if applied["safety_adjusted"]:
                                assert applied["action"] != result["choice"]
                                assert applied["safety_reason"]
                                assert applied["ledger_entry"] is None
                            else:
                                assert applied["action"] == result["choice"]
                            assert (
                                applied["applied"] and applied["external_action_executed"] is False
                            )
                            state = applied["snapshot"]
                            actions.append({"stage": row["stage"], **applied})
                        assert len(state["completed"]) == 5
                        assert (
                            state["ticket_status"] == "waiting" and state["order_status"] == "open"
                        )
                        workflows[provider] = actions
                    summary = {
                        "case": case["id"],
                        "paired_steps": len(rows),
                        "same_choice": sum(
                            row["decider"]["choice"] == row["bedrock"]["choice"] for row in rows
                        ),
                        **{
                            provider + "_total_ms": round(
                                sum(row[provider]["timings"]["backend_total_ms"] for row in rows), 3
                            )
                            for provider in ("decider", "bedrock")
                        },
                        "reference_differences": {
                            provider: sum(bool(a["policy_warning"]) for a in actions)
                            for provider, actions in workflows.items()
                        },
                        "protection_adjustments": {
                            provider: sum(a["safety_adjusted"] for a in actions)
                            for provider, actions in workflows.items()
                        },
                    }
                    observed.append({"summary": summary, "steps": rows, "workflows": workflows})
                    print(json.dumps(summary, ensure_ascii=False), flush=True)
        finally:
            request("/api/auth/logout", {})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "url": args.url,
                "note": "Observed paired model decisions and guarded sandbox workflows, not a general accuracy benchmark.",
                "cases": observed,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print("Verified four real payment workflows. Results:", args.output)


if __name__ == "__main__":
    main()
