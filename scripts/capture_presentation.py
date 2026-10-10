"""Capture the deployed payment UI and fresh live evidence; never start or stop a GPU."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

PROVIDERS = ("decider", "bedrock")
STAGES = ("intake", "verify", "approve", "execute", "close")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://d3i7ogfx5ml7dc.cloudfront.net")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("docs/presentations/v2"))
    parser.add_argument("--raw-output", type=Path, default=Path(".deployment/presentation-v2"))
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse already captured fixed runs without invoking models again",
    )
    args = parser.parse_args()
    images = args.output / "screenshots"
    images.mkdir(parents=True, exist_ok=True)
    args.raw_output.mkdir(parents=True, exist_ok=True)
    credentials = json.loads(args.credentials.read_text())
    manifest = {
        "url": args.url,
        "captured_at": datetime.now(UTC).isoformat(),
        "frontend": "crypto10",
        "api_image_tag": "20261010-loop1",
        "runs": [],
        "screenshots": [],
        "gpu_mutations": 0,
    }
    if args.resume and (args.output / "capture-manifest.json").exists():
        manifest = json.loads((args.output / "capture-manifest.json").read_text())
        manifest["resumed_at"] = datetime.now(UTC).isoformat()
    benchmark = {
        "checked_at": manifest["captured_at"],
        "application_version": {"frontend": "crypto10", "api_image_tag": "20261010-loop1"},
        "scope": "One observed batch of four initial synthetic cases, five attempted decisions per side per case. Only successful same-input pairs enter timing totals; failures are retained separately.",
        "models": {
            "decider": "StrandsAgents/strands-decider-2B-hobson-v19",
            "bedrock": "us.openai.gpt-6.1-sol",
            "bedrock_reasoning": "low",
        },
        "timing_note": "Backend sums include communication and queueing, not browser wall-clock latency. Loops are reported separately.",
        "cases": [],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1080}, device_scale_factor=1.5)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.url + "/#crypto", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".cx-case")).to_have_count(4)
        state = page.request.get(args.url + "/api/gpu").json()
        assert state["phase"] == "ready" and state["desired"] == "running", (
            "GPU must already be ready"
        )
        manifest["gpu_at_capture"] = {
            k: state.get(k) for k in ("phase", "provider", "instance_type")
        }
        page.evaluate("document.fonts.ready")

        def shot(name, selector=None, description=""):
            path = images / f"{name}.png"
            if selector:
                page.locator(selector).screenshot(path=str(path))
            else:
                page.screenshot(path=str(path))
            manifest["screenshots"] = [
                row for row in manifest["screenshots"] if row["file"] != path.name
            ]
            manifest["screenshots"].append(
                {
                    "file": path.name,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "description": description,
                    "data_replaced": False,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )

        shot("overview", description="Current production interface before a run.")
        page.locator("#gpu-open").click()
        expect(page.locator("#gpu-status")).to_have_text("GPU 就绪")
        shot(
            "gpu-dialog",
            "#gpu-dialog",
            "Shared GPU dialog, actual ready state; no lifecycle mutation.",
        )
        page.locator("#gpu-close").click()

        def run(name, kind):
            page.locator('[data-cx-mode="live"]').click()
            page.locator("[data-cx-test-kind]").select_option(kind)
            page.locator("[data-cx-start]").click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=360000)
            with page.expect_download() as download:
                page.locator("[data-cx-export]").click()
            data = json.loads(Path(download.value.path()).read_text())
            (args.raw_output / f"{name}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            manifest["runs"].append(
                {
                    "name": name,
                    "exported_at": data["exported_at"],
                    "kind": kind,
                    "source": data["runMode"],
                    "outcomes": data["businessOutcomes"],
                    "decisions": {
                        provider: len(
                            data["executions"].get(provider, {}).get("decisionHistory", [])
                        )
                        if kind == "loop"
                        else len(data["results"][provider])
                        for provider in PROVIDERS
                    },
                }
            )
            (args.output / "capture-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
            )
            print(
                "Captured",
                name,
                {p: data["businessOutcomes"][p]["complete"] for p in PROVIDERS},
                flush=True,
            )
            return data

        for case in ("pending", "underpaid", "refund", "settlement"):
            page.locator(f'[data-cx-case="{case}"]').click()
            cached = args.raw_output / f"{case}-fixed.json"
            reused = args.resume and cached.exists()
            data = json.loads(cached.read_text()) if reused else run(case + "-fixed", "workflow")
            steps = []
            for stage in STAGES:
                pair = [data["results"][p][stage] for p in PROVIDERS]
                paired = all(r.get("source") == "live" for r in pair)
                if paired:
                    assert pair[0]["input_hash"] == pair[1]["input_hash"]
                row = {"stage": stage, "paired": paired}
                for provider, result in zip(PROVIDERS, pair, strict=True):
                    execution = next(
                        (
                            r
                            for r in data["executions"].get(provider, {}).get("audit", [])
                            if r["stage"] == stage
                        ),
                        None,
                    )
                    row[provider] = {
                        **{
                            k: result.get(k)
                            for k in (
                                "choice",
                                "label",
                                "source",
                                "error",
                                "input_hash",
                                "reference_choice",
                                "reference_label",
                                "matches_reference",
                                "timings",
                                "usage",
                                "confidence",
                                "probabilities",
                            )
                        },
                        "execution": None
                        if execution is None
                        else {
                            k: execution.get(k)
                            for k in (
                                "action",
                                "requested_action",
                                "label",
                                "applied",
                                "safety_adjusted",
                                "safety_reason",
                                "ledger_entry",
                                "customer_reply",
                            )
                        },
                    }
                steps.append(row)
            successful = [r for r in steps if r["paired"]]
            summary = {"case": case, "paired_steps": len(successful)}
            for provider in PROVIDERS:
                summary[provider + "_total_ms"] = round(
                    sum(r[provider]["timings"]["backend_total_ms"] for r in successful), 3
                )
                summary[provider + "_reference_matches"] = sum(
                    r[provider]["matches_reference"] for r in successful
                )
                summary[provider + "_adjustments"] = sum(
                    bool((r[provider]["execution"] or {}).get("safety_adjusted")) for r in steps
                )
                summary[provider + "_failed_requests"] = sum(
                    bool(r[provider].get("error")) for r in steps
                )
                summary[provider + "_processed_steps"] = len(
                    data["executions"].get(provider, {}).get("snapshot", {}).get("completed", [])
                )
            benchmark["cases"].append(
                {"summary": summary, "steps": steps, "business_outcomes": data["businessOutcomes"]}
            )
            if case == "pending" and not reused:
                shot("fixed-summary", ".cx-summary", "Live same-input paired decision timings.")
                shot("fixed-table", ".cx-table-wrap", "All five live choices and actual actions.")
                shot(
                    "fixed-final",
                    "#cx-execution-results > .cx-final-grid",
                    "Processed steps versus business completion.",
                )
                for number in (1, 4):
                    shot(
                        f"fixed-turn-{number}",
                        f'[data-cx-dialogue-turn="{number}"]',
                        "Actual per-round request and both model outputs.",
                    )
                shot(
                    "customer-conversation",
                    ".cx-conversation",
                    "Template customer replies driven by actual execution.",
                )
            if case == "refund" and not reused:
                shot(
                    "refund-execute",
                    '[data-cx-dialogue-turn="4"]',
                    "Real refund suggestions and actual execution.",
                )

        loops = {}
        for case in ("pending", "refund"):
            page.locator(f'[data-cx-case="{case}"]').click()
            data = run(case + "-loop", "loop")
            loops[case] = {
                "exported_at": data["exported_at"],
                "business_outcomes": data["businessOutcomes"],
                "providers": {
                    provider: {
                        "status": data["executions"][provider]["loopState"]["status"],
                        "reason": data["executions"][provider]["loopState"]["reason"],
                        "decisions": data["executions"][provider]["decisionHistory"],
                        "events": data["executions"][provider]["events"],
                        "timeline": data["executions"][provider]["timeline"],
                        "snapshot": data["executions"][provider]["snapshot"],
                        "error": data["executions"][provider]["error"],
                    }
                    for provider in PROVIDERS
                },
            }
            shot(
                case + "-loop-summary",
                ".cx-summary",
                "Live loop totals; inputs and call counts can diverge.",
            )
            shot(
                case + "-loop-final",
                "#cx-execution-results > .cx-final-grid",
                "Actual live loop outcome, without forcing completion.",
            )
            last_run = [r for r in data["dialogues"] if r["run"] == data["dialogueRun"]]
            feedback_row = next(
                (
                    r
                    for r in last_run
                    if any(s["request"]["state"].get("feedback") for s in r["sides"].values())
                ),
                None,
            )
            if feedback_row:
                shot(
                    case + "-loop-feedback",
                    f'[data-cx-dialogue-turn="{feedback_row["number"]}"]',
                    "Request includes previous execution feedback.",
                )
            details = page.locator('[data-cx-panel="loop-history"]')
            if details.get_attribute("open") is None:
                details.locator(":scope > summary").click()
            shot(
                case + "-loop-history",
                ".cx-loop-history",
                "Every live decision, simulator event, retry and terminal state.",
            )
        page.set_viewport_size({"width": 390, "height": 900})
        page.locator(".cx-dialogue-heading").evaluate("(el) => el.scrollIntoView({block:'start'})")
        shot("mobile-dialogues", description="Current mobile view after the live refund loop.")
        page.locator("#logout-button").click()
        expect(page.locator("#login-page")).to_be_visible()
        assert not errors, errors
        browser.close()
    benchmark["totals"] = {
        provider: {
            "backend_ms": round(
                sum(c["summary"][provider + "_total_ms"] for c in benchmark["cases"]), 3
            ),
            "reference_matches": sum(
                c["summary"][provider + "_reference_matches"] for c in benchmark["cases"]
            ),
            "adjustments": sum(c["summary"][provider + "_adjustments"] for c in benchmark["cases"]),
        }
        for provider in PROVIDERS
    }
    benchmark["totals"]["gpt_over_decider"] = (
        benchmark["totals"]["bedrock"]["backend_ms"] / benchmark["totals"]["decider"]["backend_ms"]
    )
    benchmark["totals"]["paired_steps"] = sum(
        c["summary"]["paired_steps"] for c in benchmark["cases"]
    )
    benchmark["totals"]["failed_requests"] = {
        provider: sum(c["summary"][provider + "_failed_requests"] for c in benchmark["cases"])
        for provider in PROVIDERS
    }
    Path("docs/results/benchmark-2026-10-10.json").write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "loop-observations.json").write_text(
        json.dumps(loops, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "capture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print("Saved fresh live evidence and screenshots; no GPU lifecycle changes.", flush=True)


if __name__ == "__main__":
    main()
