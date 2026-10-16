"""Capture baseline/optimized three-model payment requests and sandbox results."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/presentations/v12"
PROVIDERS = ("decider", "jev", "bedrock")
STAGES = ("intake", "verify", "approve", "execute", "close")


def now():
    return datetime.now(UTC).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--url", default="https://d3i7ogfx5ml7dc.cloudfront.net")
    args = parser.parse_args()
    sources, images = OUT / "sources", OUT / "screenshots"
    sources.mkdir(parents=True, exist_ok=True)
    images.mkdir(exist_ok=True)
    path = sources / "payment-live.json"
    if path.exists():
        raise SystemExit("Evidence already exists; this command will not overwrite or rerun it.")
    credentials = json.loads(args.credentials.read_text())
    record = {
        "started_at": now(), "url": args.url + "/#crypto",
        "batch": "presentation-v12-baseline-optimized", "mode": "live",
        "design": {
            "cases": 4, "profiles": ["baseline", "optimized"], "providers": list(PROVIDERS),
            "stages": list(STAGES), "planned_formal_calls": 120, "planned_warmup_calls": 6,
            "order": "Baseline then optimized within each case; not randomized or repeated.",
            "execution": "Browser sandbox only; no real funds or chain transactions.",
        },
        "warmups": [], "cases": {}, "http_decisions": [], "page_errors": [], "gpu_writes": [],
    }
    manifest = {"created_at": now(), "screenshots": [], "editing": "Actual browser screenshots; no UI data replaced."}
    phase = "setup"

    def save():
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        (OUT / "capture-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    with sync_playwright() as p:
        executable = Path("/home/ec2-user/.cache/ms-playwright/chromium-1243/chrome-linux-arm64/chrome")
        browser = p.chromium.launch(headless=True, executable_path=str(executable) if executable.exists() else None)
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1.5)
        page.on("pageerror", lambda error: record["page_errors"].append(str(error)))

        def deny_gpu(route):
            record["gpu_writes"].append(route.request.url)
            route.fulfill(status=409, json={"detail": "Presentation capture does not change GPU lifecycle"})

        def response(res):
            if "/api/crypto/decision" not in res.url:
                return
            try:
                record["http_decisions"].append({
                    "captured_at": now(), "phase": phase, "status": res.status,
                    "request": res.request.post_data_json, "response": res.json(),
                })
                save()
            except Exception as error:
                record.setdefault("capture_errors", []).append(type(error).__name__)

        page.route("**/api/gpu/start", deny_gpu)
        page.route("**/api/gpu/stop", deny_gpu)
        page.on("response", response)
        try:
            page.goto(record["url"], wait_until="domcontentloaded")
            page.locator("#login-username").fill(credentials["username"])
            page.locator("#login-password").fill(credentials["password"])
            page.locator("#login-submit").click()
            expect(page.locator(".cx-case")).to_have_count(4, timeout=30000)
            status = page.request.get(args.url + "/api/gpu").json()
            record["gpu"] = {k: status.get(k) for k in ("phase", "provider", "instance_type")}
            assert status["phase"] == "ready", "The existing GPU is not ready; no lifecycle changes were attempted."
            page.evaluate("document.fonts.ready")
            old = json.loads((ROOT / "docs/presentations/v8/live-observations.json").read_text())
            phase = "warmup"
            for profile in ("baseline", "optimized"):
                for provider in PROVIDERS:
                    request = {
                        "snapshot": old["cases"]["pending"]["snapshot"], "stage": "intake",
                        "provider": provider, "mode": "live", "input_profile": profile,
                    }
                    warm = page.evaluate(
                        """async (body) => {
                            const start = performance.now();
                            const res = await fetch('/api/crypto/decision', {
                                method: 'POST', credentials: 'same-origin', cache: 'no-store',
                                headers: {'Content-Type': 'application/json', 'X-Decider-Client': 'web'},
                                body: JSON.stringify(body)
                            });
                            return {status: res.status, result: await res.json(), client_ms: performance.now()-start};
                        }""", request,
                    )
                    record["warmups"].append({"request": request, **warm})
                    save()
                    assert warm["status"] == 200 and warm["result"].get("source") == "live"
                    print("Warmup", profile, provider, "ok", flush=True)

            phase = "formal"
            record["formal_started_at"] = now()

            def shot(name, selector):
                target = images / f"{name}.png"
                page.locator(selector).screenshot(path=str(target), timeout=15000)
                manifest["screenshots"].append({
                    "file": str(target.relative_to(ROOT)), "selector": selector,
                    "captured_at": now(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "data_replaced": False,
                })
                save()

            for case in ("pending", "underpaid", "refund", "settlement"):
                record["cases"][case] = {}
                for profile, method in (("baseline", "workflow"), ("optimized", "optimized")):
                    page.locator(f'[data-cx-case="{case}"]').click()
                    page.locator('[data-cx-mode="live"]').click()
                    page.locator("[data-cx-test-kind]").select_option(method)
                    page.locator("[data-cx-start]").click()
                    expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=240000)
                    expect(page.locator(".cx-turn-pending")).to_have_count(0)
                    with page.expect_download() as download:
                        page.locator("[data-cx-export]").click()
                    data = json.loads(Path(download.value.path()).read_text())
                    record["cases"][case][profile] = data
                    save()
                    assert data["comparisonProviders"] == list(PROVIDERS)
                    assert data["workflowKind"] == ("fixed" if profile == "baseline" else "optimized")
                    for stage in STAGES:
                        rows = [data["results"][p][stage] for p in PROVIDERS]
                        assert all(r.get("source") == "live" and r["input_profile"] == profile for r in rows)
                        assert len({r["input_hash"] for r in rows}) == 1
                        assert all(r["model_input"] == rows[0]["model_input"] for r in rows)
                    if profile == "optimized":
                        assert data["snapshot"] == record["cases"][case]["baseline"]["snapshot"]
                    print(case, profile, {
                        p: {"matches": sum(r["matches_reference"] for r in data["results"][p].values()),
                            "ms": round(sum(r["timings"]["backend_total_ms"] for r in data["results"][p].values()), 1)}
                        for p in PROVIDERS
                    }, flush=True)
                    page.locator(".cx-dialogue-feed").evaluate("(el) => el.scrollTop = 0")
                    if case in ("pending", "refund"):
                        shot(f"{case}-{profile}-approve", '[data-cx-dialogue-turn="3"]')
                        shot(f"{case}-{profile}-summary", ".cx-summary")
                    if case == "pending":
                        for provider in PROVIDERS:
                            panel = page.locator(f'[data-cx-panel="outcome-{provider}"]')
                            if panel.get_attribute("open") is None:
                                panel.locator("summary").click()
                        shot(f"{case}-{profile}-outcomes", "#cx-execution-results > .cx-final-grid")
            record["finished_at"] = now()
            formal = [r for r in record["http_decisions"] if r["phase"] == "formal"]
            assert len(formal) == 120 and all(r["status"] == 200 for r in formal)
            assert not record["page_errors"] and not record["gpu_writes"] and not record.get("capture_errors")
            record["complete"] = True
            save()
            manifest["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            save()
            print("Saved 120 formal real calls, 6 warmups, screenshots and sandbox outcomes.", flush=True)
        except Exception as error:
            record["complete"] = False
            record["failure"] = {"type": type(error).__name__, "message": str(error), "at": now()}
            save()
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
