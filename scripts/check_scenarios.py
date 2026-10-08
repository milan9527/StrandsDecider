"""Run catalog scenarios through the real API and save observed results, not expected predictions."""

import argparse
import http.cookiejar
import json
import urllib.request
from pathlib import Path

from app.main import validate_response
from app.schemas import DecisionRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--ids", nargs="+", help="Only run these catalog IDs; default: all")
    parser.add_argument(
        "--output", type=Path, default=Path(".deployment/scenario-verification.json")
    )
    args = parser.parse_args()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            args.url.rstrip("/") + path,
            data=data,
            headers={"Content-Type": "application/json", "X-Decider-Client": "web"} if data else {},
        )
        with opener.open(req, timeout=195) as response:
            return json.load(response)

    request("/api/auth/login", json.loads(args.credentials.read_text()))
    observed = []
    try:
        catalog = request("/api/examples")
        if args.ids:
            missing = set(args.ids) - {example["id"] for example in catalog}
            if missing:
                raise ValueError(f"Catalog is missing requested scenarios: {sorted(missing)}")
        selected = [e for e in catalog if not args.ids or e["id"] in args.ids]
        for example in selected:
            body = DecisionRequest(
                mode="live",
                measure_decisions=True,
                example_id=example["id"],
                state=example["state"],
                questions=example["questions"],
            )
            result = request("/api/decide", body.model_dump(exclude_none=True))
            assert result["source"] == "live"
            validate_response(result, body.wire_payload()["questions"])
            timings = result["timings"]
            assert timings["execution"] == "individual"
            assert set(timings["decisions_ms"]) == set(example["questions"])
            assert all(elapsed > 0 for elapsed in timings["decisions_ms"].values())
            assert timings["backend_total_ms"] >= sum(timings["decisions_ms"].values()) - 0.01
            observed.append({"id": example["id"], "title": example["title"], "result": result})
            decisions = {
                key: answer.get("choice", answer.get("noul", answer.get("score")))
                for key, answer in result["answers"].items()
            }
            print(
                json.dumps(
                    {
                        "scenario": example["id"],
                        "decisions": decisions,
                        "total_ms": timings["backend_total_ms"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        request("/api/auth/logout", {})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "url": args.url,
                "catalog_size": len(catalog),
                "verified": observed,
                "note": "Observed model outputs; this verifies execution and response structure, not model accuracy.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(f"Verified {len(observed)} real scenarios. Results: {args.output}")


if __name__ == "__main__":
    main()
