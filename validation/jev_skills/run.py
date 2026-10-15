"""Isolated, paired Jev/Decider validation; never applies model-selected actions."""

import argparse
import copy
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.jev import ENDPOINT, MODEL, JevClient  # noqa: E402
from app.main import validate_response  # noqa: E402
from app.schemas import DecisionRequest  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def wire_payload(request):
    state = request["state"]
    body = {
        "state": state if isinstance(state, str) else canonical(state),
        "questions": copy.deepcopy(request["questions"]),
    }
    # Apply the existing application contract to both arms before any request.
    validated = DecisionRequest(mode="live", **body).wire_payload()
    if body != validated:
        raise ValueError("Application validation would change the paired input")
    return body


def load_cases():
    source = read(HERE / "source.json")
    expectations = read(HERE / "expectations.json")
    cases = []
    templates = {}
    for asset in source["assets"]:
        path = HERE / asset["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError(f"Upstream asset changed: {asset['path']}")
        if not asset["request"]:
            continue
        case_id = path.stem
        request = read(path)
        templates[case_id] = request
        cases.append({
            "id": case_id,
            "skill": case_id.split("--")[0],
            "kind": "upstream_template",
            "source_path": asset["source_path"],
            "payload": wire_payload(request),
            "expected": expectations["templates"][case_id],
        })
    for edge in read(HERE / "fixtures/edge_cases.json"):
        request = copy.deepcopy(templates[edge["base"]])
        request["state"] = edge["state"]
        cases.append({
            "id": edge["id"],
            "skill": edge["base"].split("--")[0],
            "kind": "authored_counterfactual",
            "base": edge["base"],
            "reason": edge["reason"],
            "payload": wire_payload(request),
            "expected": edge["expected"],
        })
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    for case in cases:
        if set(case["payload"]["questions"]) != set(case["expected"]):
            raise ValueError(f"Expected question IDs differ: {case['id']}")
        for name, expected in case["expected"].items():
            q = case["payload"]["questions"][name]
            if expected is None:
                continue
            if q["type"] == "choice" and expected not in q["criteria"]:
                raise ValueError("Expected choice outside supplied candidates")
            if q["type"] == "noul" and type(expected) is not bool:
                raise ValueError("Expected Noul must be boolean")
            if q["type"] == "score" and (
                type(expected) is not int or not 0 <= expected < len(q["criteria"])
            ):
                raise ValueError("Expected score must be a rubric index")
        case["input_sha256"] = digest(case["payload"])
    return source, expectations, cases


def validate_raw(data, payload):
    validate_response(data, payload["questions"])
    # Python bool is a subclass of int; do not accept it as a numeric probability.
    for answer in data["answers"].values():
        numbers = list(answer.get("probabilities", {}).values())
        numbers += [answer[k] for k in ("noul", "confidence", "score") if k in answer]
        if any(type(value) not in (int, float) for value in numbers):
            raise ValueError("Boolean or nonnumeric response value")
    if not data["model"].strip() or len(data["model"]) > 120:
        raise ValueError("Invalid model identifier")


def assess(case, data):
    judgments = {}
    for name, question in case["payload"]["questions"].items():
        answer = data["answers"][name]
        expected = case["expected"][name]
        kind = question["type"]
        value = answer[kind]
        if kind == "choice":
            match = value == expected
        elif kind == "noul":
            match = value != 0.5 and (value > 0.5) == expected
        else:
            match = abs(value - expected) <= 0.5 if expected is not None else None
        judgments[name] = {
            "type": kind, "value": value, "expected": expected,
            "matches_reference": match if expected is not None else None,
        }
    return judgments


def collect(provider, case, invoke):
    started = perf_counter()
    result = {
        "provider": provider,
        "input_sha256": case["input_sha256"],
        "requested_model": MODEL if provider == "jev" else "deployment-configured Decider",
        "estimated_request_usd": None,
    }
    raw = None
    try:
        # Never send case IDs, reference labels, or assessment metadata to a model.
        raw = invoke(copy.deepcopy(case["payload"]))
        validate_raw(raw, case["payload"])
        if provider == "decider" and raw.get("source") != "live":
            raise ValueError("Decider did not return a live inference receipt")
        result.update(
            status="ok", response=raw, resolved_model=raw["model"],
            judgments=assess(case, raw),
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
        # Exception messages/HTTP bodies can contain credentials or proxy content.
        result.update(status="error", error_type=type(exc).__name__)
        if isinstance(exc, httpx.HTTPStatusError):
            result["http_status"] = exc.response.status_code
        elif raw is not None:
            result["invalid_response"] = raw
    result["client_elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
    return result


def run_pairs(cases, providers, repeats, write_receipt):
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for repeat in range(repeats):
            for index, case in enumerate(cases):
                # Alternate submission order; at most one in-flight request per provider.
                order = ("jev", "decider") if (repeat + index) % 2 else ("decider", "jev")
                futures = {
                    name: pool.submit(collect, name, case, providers[name]) for name in order
                }
                row = {
                    "case_id": case["id"], "skill": case["skill"], "repeat": repeat + 1,
                    "input_sha256": case["input_sha256"],
                    "providers": {name: future.result() for name, future in futures.items()},
                }
                write_receipt(row)
                rows.append(row)
    return rows


def summarize(cases, rows, repeats):
    by_id = {case["id"]: case for case in cases}
    result = {}
    for provider in ("jev", "decider"):
        stats = {}
        for skill in ["all", *sorted({case["skill"] for case in cases})]:
            selected = [row for row in rows if skill == "all" or row["skill"] == skill]
            calls = [row["providers"][provider] for row in selected]
            good = [call for call in calls if call["status"] == "ok"]
            judgments = [j for call in good for j in call["judgments"].values()]
            planned = [c for c in cases if skill == "all" or c["skill"] == skill]
            latency = [call["client_elapsed_ms"] for call in good]
            stats[skill] = {
                "planned_calls": len(planned) * repeats,
                "attempted_calls": len(calls),
                "valid_calls": len(good),
                "failed_calls": len(calls) - len(good),
                "planned_questions": sum(len(c["expected"]) for c in planned) * repeats,
                "reference_questions": sum(
                    sum(v is not None for v in c["expected"].values()) for c in planned
                ) * repeats,
                "matches_reference": sum(j["matches_reference"] is True for j in judgments),
                "reference_mismatches": sum(j["matches_reference"] is False for j in judgments),
                "unscored_questions_returned": sum(
                    j["matches_reference"] is None for j in judgments
                ),
                "resolved_models": sorted({c["resolved_model"] for c in good}),
                "mean_client_ms": round(statistics.mean(latency), 3) if latency else None,
                "median_client_ms": round(statistics.median(latency), 3) if latency else None,
                "p95_client_ms": sorted(latency)[math.ceil(len(latency) * 0.95) - 1] if latency else None,
                "total_client_ms": round(sum(latency), 3),
            }
        result[provider] = stats
    valid_pairs = [
        row for row in rows
        if all(r["status"] == "ok" for r in row["providers"].values())
        and len({r["input_sha256"] for r in row["providers"].values()}) == 1
    ]
    result["pairing"] = {
        "planned_pairs": len(cases) * repeats,
        "valid_identical_input_pairs": len(valid_pairs),
        "valid_paired_questions": sum(len(by_id[r["case_id"]]["expected"]) for r in valid_pairs),
    }
    result["mismatches"] = [
        {"case_id": row["case_id"], "repeat": row["repeat"], "provider": provider,
         "question": name, **judgment}
        for row in rows for provider, call in sorted(row["providers"].items())
        for name, judgment in sorted(call.get("judgments", {}).items())
        if judgment["matches_reference"] is False
    ]
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def offline_source_check(source_dir, source):
    """Run the upstream CLI in dry-run mode, without installing any skills."""
    if source_dir is None:
        return {"upstream_cli": "not_run; specify --upstream-source"}
    script = source_dir / "skills/jev/scripts/jev.py"
    results = []
    for asset in source["assets"]:
        if not asset["request"]:
            continue
        run = subprocess.run(
            [sys.executable, str(script), "decide", str(HERE / asset["path"]),
             "--provider", "typesafe", "--dry-run"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if run.returncode:
            raise ValueError(f"Upstream dry-run failed: {asset['source_path']}")
        parsed = json.loads(run.stdout)
        if wire_payload(parsed) != wire_payload(read(HERE / asset["path"])):
            raise ValueError("Upstream CLI changed state/questions")
        results.append({"source_path": asset["source_path"], "exit_code": run.returncode})
    return {"upstream_cli": "dry_run_only", "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make real paired model calls")
    parser.add_argument("--url", help="Existing Decider application URL")
    parser.add_argument("--credentials", type=Path, help="Existing application login JSON")
    parser.add_argument("--jev-key-file", type=Path, help="Existing server-side TypeSafe key")
    parser.add_argument("--upstream-source", type=Path, help="Pinned source for offline CLI checks")
    parser.add_argument("--output", type=Path, required=True, help="New directory; refuses overwrite")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-calls", type=int, default=64)
    args = parser.parse_args()
    source, expectations, cases = load_cases()
    if args.repeats < 1 or len(cases) * 2 * args.repeats > args.max_calls:
        parser.error("Planned requests exceed --max-calls, or --repeats is invalid")
    if args.live and not all((args.url, args.credentials)):
        parser.error("--live requires --url and --credentials")
    key = None
    if args.live:
        key = (
            args.jev_key_file.expanduser().read_text().strip()
            if args.jev_key_file else os.getenv("JEV_API_KEY", "").strip()
        )
        if not key:
            parser.error("Jev key is missing; set --jev-key-file or JEV_API_KEY")
    args.output.mkdir(parents=True, exist_ok=False)
    plan = {
        "created_at": datetime.now(UTC).isoformat(), "mode": "live" if args.live else "offline",
        "source_commit": source["commit"], "expectation_method": expectations["method"],
        "repeats": args.repeats, "max_calls": args.max_calls,
        "planned_calls": len(cases) * 2 * args.repeats,
        "question_types": dict(Counter(
            q["type"] for case in cases for q in case["payload"]["questions"].values()
        )),
        "external_action_executed": False,
        "cases": cases,
    }
    # Freeze inputs and labels before any paid inference.
    write_json(args.output / "plan.json", plan)
    offline = offline_source_check(args.upstream_source, source)
    offline.update(
        assets_verified=len(source["assets"]), readme_scenarios=len(source["scenarios"]),
        templates=sum(c["kind"] == "upstream_template" for c in cases),
        counterfactuals=sum(c["kind"] == "authored_counterfactual" for c in cases),
        application_request_validation="passed",
    )
    write_json(args.output / "offline.json", offline)
    if not args.live:
        print(json.dumps(offline, ensure_ascii=False))
        return 0

    jev = JevClient(api_key=key)
    assert jev.http is not None
    rows = []
    with httpx.Client(
        base_url=args.url, headers={"X-Decider-Client": "web"},
        timeout=httpx.Timeout(55, connect=5), trust_env=False, follow_redirects=False,
    ) as decider:
        logged_in = False
        try:
            response = decider.post("/api/auth/login", json=read(args.credentials))
            response.raise_for_status()
            logged_in = True
            response = decider.get("/api/health")
            response.raise_for_status()
            health = response.json()
            write_json(args.output / "health.json", health)
            if not health.get("connected"):
                raise ValueError("Existing Decider service is not ready; no GPU lifecycle changes made")

            def invoke_decider(payload):
                response = decider.post("/api/decide", json={"mode": "live", **payload})
                response.raise_for_status()
                return response.json()

            def invoke_jev(payload):
                # Reuse the project's key handling/HTTP transport, preserving all
                # question names and all three types instead of flattening to action.
                with jev.http.stream("POST", ENDPOINT, json={**payload, "model": MODEL}) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 1_048_576:
                            raise ValueError("Jev response exceeds 1 MiB")
                return json.loads(content)

            with (args.output / "receipts.jsonl").open("x") as receipts:
                def record(row):
                    receipts.write(canonical(row) + "\n")
                    receipts.flush()
                    print(row["case_id"], {
                        p: value["status"] for p, value in row["providers"].items()
                    }, flush=True)

                rows = run_pairs(cases, {"jev": invoke_jev, "decider": invoke_decider},
                                 args.repeats, record)
        finally:
            jev.close()
            if logged_in:
                try:
                    decider.post("/api/auth/logout", json={}).raise_for_status()
                except httpx.HTTPError:
                    print("Session logout failed; no credentials included in receipts.", file=sys.stderr)
    summary = summarize(cases, rows, args.repeats)
    write_json(args.output / "summary.json", summary)
    print(json.dumps({p: summary[p]["all"] for p in ("jev", "decider")}, ensure_ascii=False))
    # Semantic disagreements are findings; missing or malformed responses fail the run.
    return 0 if summary["pairing"]["valid_identical_input_pairs"] == len(cases) * args.repeats else 1


if __name__ == "__main__":
    raise SystemExit(main())
