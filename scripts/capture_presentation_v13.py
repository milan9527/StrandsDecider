"""Capture one routing task and execute each selected target once."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/presentations/v13"
PROVIDERS = ("decider", "jev", "bedrock")


def now():
    return datetime.now(UTC).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--url", default="https://d3i7ogfx5ml7dc.cloudfront.net")
    parser.add_argument("--case", choices=("analysis", "support"), default="analysis")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    output = args.output.resolve()
    case_id = args.case
    prefix = "settlement" if case_id == "analysis" else "support"
    sources, screenshots = output / "sources", output / "screenshots"
    sources.mkdir(parents=True, exist_ok=True)
    screenshots.mkdir(exist_ok=True)
    dest = sources / f"{prefix}-live.json"
    if dest.exists():
        raise SystemExit("Capture exists; preserve it rather than silently rerunning.")
    credentials = json.loads(args.credentials.read_text())
    data = {"started_at": now(), "url": args.url + "/#routing", "warmups": [],
            "calls": [], "page_errors": [], "gpu_writes": [],
            "case": case_id,
            "method": f"One {case_id} task, six excluded warmups, six formal routing decisions, "
                      "then each of three selected targets executed once. No retries or substitutions.",
            "target_scope": "Text analysis only, no money transfer or external ledger action."}
    manifest = {"screenshots": [], "editing": "Actual UI screenshots; no response data replaced."}
    phase = "setup"

    def save():
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        (output / "capture-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    with sync_playwright() as pw:
        executable = Path("/home/ec2-user/.cache/ms-playwright/chromium-1243/chrome-linux-arm64/chrome")
        browser = pw.chromium.launch(headless=True, executable_path=str(executable))
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1.5)
        page.on("pageerror", lambda e: data["page_errors"].append(str(e)))

        def deny(route):
            data["gpu_writes"].append(route.request.url)
            route.fulfill(status=409, json={"detail": "Capture prohibits GPU lifecycle changes"})

        def capture(response):
            if response.url.endswith(("/api/routing/decision", "/api/routing/execute")):
                data["calls"].append({"captured_at": now(), "phase": phase, "url": response.url,
                                      "status": response.status, "request": response.request.post_data_json,
                                      "response": response.json()})
                save()

        def shot(name, selector):
            path = screenshots / f"{name}.png"
            page.locator(selector).screenshot(path=str(path), timeout=30000)
            manifest["screenshots"].append({"file": str(path.relative_to(ROOT)), "selector": selector,
                                            "captured_at": now(), "data_replaced": False,
                                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            save()

        def export(name):
            with page.expect_download() as download:
                page.locator("[data-rt-export]").click()
            data[name] = json.loads(Path(download.value.path()).read_text())
            save()

        page.route("**/api/gpu/start", deny)
        page.route("**/api/gpu/stop", deny)
        page.on("response", capture)
        try:
            page.goto(data["url"], wait_until="domcontentloaded")
            page.locator("#login-username").fill(credentials["username"])
            page.locator("#login-password").fill(credentials["password"])
            page.locator("#login-submit").click()
            expect(page.locator(".rt-case")).to_have_count(4, timeout=30000)
            status = page.request.get(args.url + "/api/gpu").json()
            data["gpu"] = {k: status.get(k) for k in ("phase", "provider", "instance_type")}
            assert status["phase"] == "ready"
            catalog = page.request.get(args.url + "/api/routing/catalog").json()
            task = next(c["task"] for c in catalog["cases"] if c["id"] == case_id)
            data["task"] = task
            phase = "warmup"
            for provider in PROVIDERS:
                workflow = None
                for stage in ("workflow", "model"):
                    body = {"task": {"text": task}, "provider": provider, "stage": stage,
                            "mode": "live", "catalog_version": catalog["version"],
                            "ranking_version": catalog["rankings"]["version"]}
                    if workflow:
                        body["workflow"] = workflow
                    result = page.evaluate("""async body => {
                        const r = await fetch('/api/routing/decision', {
                          method:'POST', credentials:'same-origin',
                          headers:{'Content-Type':'application/json','X-Decider-Client':'web'},
                          body:JSON.stringify(body)
                        });
                        return {status:r.status,result:await r.json()};
                    }""", body)
                    data["warmups"].append({"request": body, **result})
                    save()
                    assert result["status"] == 200
                    workflow = result["result"]["choice"]
                    print("Warmup", provider, stage, "ok", flush=True)
            phase = "routing"
            page.locator(f'[data-rt-case="{case_id}"]').click()
            page.locator("[data-rt-mode]").select_option("live")
            page.locator("[data-rt-start]").click()
            expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=150000)
            export("routing_export")
            page.evaluate("document.fonts.ready")
            shot(f"{prefix}-routing", "#rt-results > .rt-sides")
            shot(f"{prefix}-request", '[data-rt-stage="workflow"] > .rt-turn-input')
            for provider in PROVIDERS:
                side = data["routing_export"]["cases"][case_id]["sides"][provider]
                assert not side["error"] and len(side["steps"]) == 2
                print("Route", provider, side["steps"][-1]["selected_model"]["name"],
                      round(sum(r["timings"]["backend_total_ms"] for r in side["steps"]), 1), flush=True)
                phase = "target-" + provider
                with page.expect_response(lambda r: r.url.endswith("/api/routing/execute"), timeout=65000):
                    page.locator(f'[data-rt-execute="{provider}"]').click()
                expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=65000)
                shot(f"{prefix}-target-{provider}", f'[data-rt-side="{provider}"] > .rt-execution')
                export("executed_export")
                result = data["executed_export"]["cases"][case_id]["sides"][provider]["execution"]
                print("Target", provider, "complete", result.get("complete"),
                      "ms", result.get("backend_total_ms"), "error", result.get("error"), flush=True)
            shot(f"{prefix}-executed", "#rt-results > .rt-sides")
            data["finished_at"] = now()
            data["complete"] = True
            save()
            manifest["evidence_sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
            save()
        finally:
            browser.close()
    print("Saved routing, three target results and actual screenshots.", flush=True)


if __name__ == "__main__":
    main()
