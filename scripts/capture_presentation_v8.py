"""Prewarm all providers, then capture four live comparison cases for PPT v8."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/presentations/v8"
PROVIDERS = ("decider", "jev", "bedrock")
STAGES = ("intake", "verify", "approve", "execute", "close")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--url", default="https://d3i7ogfx5ml7dc.cloudfront.net")
    args = parser.parse_args()
    images = OUT / "screenshots"
    images.mkdir(parents=True, exist_ok=True)
    evidence = OUT / "live-observations.json"
    # Never accidentally replace measurements by rerunning a screenshot command.
    if evidence.exists():
        raise SystemExit("This version already has observations; use a new output version.")
    credentials = json.loads(args.credentials.read_text())
    records = {
        "captured_at": datetime.now(UTC).isoformat(),
        "url": args.url + "/#crypto",
        "batch": "presentation-v8-warm",
        "mode": "live",
        "input_profile": "optimized",
        "cases": {},
        "loops": {},
        "warmups": [],
        "measurement_method": "One unmeasured intake request per provider before all 60 measured calls; no latency subtraction.",
    }
    manifest = {
        "captured_at": records["captured_at"],
        "url": records["url"],
        "screenshots": [],
        "editing": "Browser screenshots and rectangular crops only; no UI data replaced.",
    }
    errors, gpu_writes = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1.5)
        page.on("pageerror", lambda e: errors.append(str(e)))

        def prohibit_gpu(route):
            gpu_writes.append(route.request.url)
            route.fulfill(status=409, json={"detail": "Capture cannot change GPU lifecycle"})

        page.route("**/api/gpu/start", prohibit_gpu)
        page.route("**/api/gpu/stop", prohibit_gpu)
        page.goto(records["url"], wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".cx-case")).to_have_count(4)
        status = page.request.get(args.url + "/api/gpu").json()
        assert status["phase"] == "ready", "Existing GPU must already be ready."
        manifest["gpu"] = {key: status.get(key) for key in ("phase", "provider", "instance_type")}
        page.evaluate("document.fonts.ready")

        previous = json.loads((ROOT / "docs/presentations/v7/live-observations.json").read_text())
        for provider in PROVIDERS:
            request = {
                "snapshot": previous["cases"]["pending"]["snapshot"],
                "stage": "intake",
                "provider": provider,
                "mode": "live",
                "input_profile": "optimized",
            }
            warm = page.evaluate(
                """async (body) => {
                    const startedAt = new Date().toISOString(), start = performance.now();
                    const response = await fetch('/api/crypto/decision', {
                        method: 'POST', credentials: 'same-origin', cache: 'no-store',
                        headers: {'Content-Type': 'application/json', 'X-Decider-Client': 'web'},
                        body: JSON.stringify(body)
                    });
                    return {startedAt, elapsedMs: performance.now() - start,
                            status: response.status, result: await response.json()};
                }""",
                request,
            )
            records["warmups"].append({"request": request, **warm})
            evidence.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            assert warm["status"] == 200 and warm["result"].get("source") == "live"
            print("Warmup", provider, warm["result"]["timings"]["backend_total_ms"], flush=True)
        records["measured_started_at"] = datetime.now(UTC).isoformat()

        def shot(name, selector=None, description=""):
            path = images / f"{name}.png"
            if selector:
                page.locator(selector).screenshot(path=str(path), timeout=15000)
            else:
                page.screenshot(path=str(path))
            manifest["screenshots"].append(
                {
                    "file": str(path.relative_to(OUT)),
                    "selector": selector,
                    "description": description,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "data_replaced": False,
                }
            )
            (OUT / "capture-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
            )

        def run(case, method):
            page.locator(f'[data-cx-case="{case}"]').click()
            page.locator('[data-cx-mode="live"]').click()
            page.locator("[data-cx-test-kind]").select_option(method)
            page.locator("[data-cx-start]").click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=240000)
            expect(page.locator(".cx-turn-pending")).to_have_count(0)
            with page.expect_download() as download:
                page.locator("[data-cx-export]").click()
            data = json.loads(Path(download.value.path()).read_text())
            assert data["comparisonProviders"] == list(PROVIDERS)
            bucket = "loops" if method == "loop" else "cases"
            records[bucket][case] = data
            evidence.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            return data

        for case, stage in (
            ("pending", "verify"),
            ("underpaid", "verify"),
            ("refund", "approve"),
            ("settlement", "verify"),
        ):
            data = run(case, "optimized")
            for provider in PROVIDERS:
                assert len(data["executions"].get(provider, {}).get("audit", [])) == 5
            for step in STAGES:
                results = [data["results"][provider][step] for provider in PROVIDERS]
                assert all(r.get("source") == "live" and not r.get("error") for r in results)
                assert len({r["input_hash"] for r in results}) == 1
                assert all(r["model_input"] == results[0]["model_input"] for r in results)
            page.locator(".cx-dialogue-feed").evaluate("(el) => el.scrollTop = 0")
            page.evaluate("window.scrollTo(0, 0)")
            shot(case + "-overview", description=f"{case}: optimized live run, actual UI.")
            shot(case + "-timings", ".cx-summary", f"{case}: five-step totals.")
            turn = STAGES.index(stage) + 1
            selector = f'[data-cx-dialogue-turn="{turn}"]'
            shot(case + "-decision", selector, f"{case}: actual {stage} input/output.")
            shot(
                case + "-outputs",
                selector + " .cx-turn-pair",
                f"{case}: three actual {stage} outputs and execution results.",
            )
            for provider in PROVIDERS:
                panel = page.locator(f'[data-cx-panel="outcome-{provider}"]')
                if panel.get_attribute("open") is None:
                    panel.locator("summary").click()
            shot(
                case + "-outcomes",
                "#cx-execution-results > .cx-final-grid",
                f"{case}: actual final outcomes and customer replies.",
            )
            print(
                case,
                {
                    provider: {
                        "ms": round(
                            sum(
                                r["timings"]["backend_total_ms"]
                                for r in data["results"][provider].values()
                            ),
                            3,
                        ),
                        "reference": sum(
                            r["matches_reference"] for r in data["results"][provider].values()
                        ),
                    }
                    for provider in PROVIDERS
                },
                flush=True,
            )

        records["measured_finished_at"] = datetime.now(UTC).isoformat()
        # Reuse the independently documented loop; it is not part of warm speed tests.
        records["loops"] = previous["loops"]
        records["loop_source"] = {
            "file": "../v7/live-observations.json",
            "captured_at": previous["captured_at"],
            "sha256": hashlib.sha256(
                (ROOT / "docs/presentations/v7/live-observations.json").read_bytes()
            ).hexdigest(),
            "new_calls_in_this_batch": 0,
        }
        previous_manifest = json.loads(
            (ROOT / "docs/presentations/v7/capture-manifest.json").read_text()
        )
        for item in previous_manifest["screenshots"]:
            if "pending-loop-" in item["file"]:
                manifest["screenshots"].append({**item, "reused_from": "../v7/" + item["file"]})
        assert not gpu_writes and not errors, (gpu_writes, errors)
        records["verification"] = {"page_errors": errors, "gpu_writes": gpu_writes}
        evidence.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        manifest["evidence_sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
        (OUT / "capture-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        browser.close()
    print("Captured 60 measured calls after 3 warmups; reused prior independent loop evidence.")


if __name__ == "__main__":
    main()
