"""Exercise authenticated GPU controls and observe asynchronous startup or shutdown."""

import argparse
import json
import os
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument(
        "--action", choices=["start", "stop", "observe-stop", "observe-ready"], required=True
    )
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        options = {"headless": True}
        if os.getenv("CHROMIUM_PATH"):
            options["executable_path"] = os.environ["CHROMIUM_PATH"]
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        page.locator("#gpu-open").click()
        expect(page.locator("#gpu-panel")).to_be_visible()
        expect(page.locator("#gpu-panel")).to_contain_text("按需")
        expect(page.locator(".scenario-card")).to_have_count(16)
        started = time.monotonic()
        if not args.action.startswith("observe-"):
            expect(page.locator("#gpu-" + args.action)).to_be_enabled(timeout=10000)
            page.locator("#gpu-" + args.action).click()
            expect(page.locator("#gpu-" + args.action)).to_be_disabled()
        target = "ready" if args.action in ("start", "observe-ready") else "stopped"
        deadline = time.monotonic() + 1500
        previous = None
        while time.monotonic() < deadline:
            response = page.request.get(args.url + "/api/gpu")
            assert response.ok
            state = response.json()
            assert state["enabled"] and state["purchase_option"] == "on-demand"
            if state["phase"] != previous:
                print(json.dumps(state, ensure_ascii=False), flush=True)
                previous = state["phase"]
            assert state["phase"] != "error", state
            if state["phase"] == target:
                break
            page.wait_for_timeout(5000)
        else:
            raise TimeoutError("GPU did not reach " + target)
        elapsed = time.monotonic() - started
        expect(page.locator("#gpu-status")).to_have_text(
            "GPU 就绪" if target == "ready" else "已停止", timeout=15000
        )
        if state.get("provider") == "sagemaker":
            expect(page.locator("#gpu-heading-label")).to_contain_text("SageMaker")
        elif state.get("idle_auto_stop") is False:
            assert state["idle_remaining_seconds"] is None
            expect(page.locator("#gpu-spec")).to_contain_text("持续运行")
            expect(page.locator("#gpu-spec")).not_to_contain_text("闲置 30 分钟")
            expect(page.locator("#gpu-stop")).to_have_text("停止 GPU，保留磁盘")
        if target == "stopped":
            assert state["instance_count"] == 0
            if state["instance_id"] and state.get("provider") != "sagemaker":
                assert state["disk_retained"] and state["instance_state"] == "stopped"
            page.locator("#gpu-close").click()
            page.locator('#page-playground [data-mode="live"]').click()
            page.locator("#run-decision").click()
            expect(page.locator("#toast")).to_contain_text("GPU 尚未就绪")
            expect(page.locator("#gpu-dialog")).to_be_visible()
            page.locator("#gpu-close").click()
            page.locator('#page-playground [data-mode="example"]').click()
            page.locator("#run-decision").click()
            expect(page.locator("#results .answer-card")).to_have_count(3)
            assert page.request.get(args.url + "/api/ready").status == 200
            page.locator("#gpu-open").click()
        page.screenshot(path=str(artifacts / f"gpu-{target}-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#gpu-panel").screenshot(path=str(artifacts / f"gpu-{target}-mobile.png"))
        page.set_viewport_size({"width": 320, "height": 740})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#gpu-close").click()
        page.locator("#logout-button").click()
        expect(page.locator("#login-page")).to_be_visible()
        assert not errors, errors
        browser.close()
    print(
        json.dumps(
            {
                "action": args.action,
                "phase": target,
                "elapsed_seconds": round(elapsed, 1),
                "instance_id": state["instance_id"],
                "disk_retained": state["disk_retained"],
            }
        ),
        flush=True,
    )
    print("GPU browser check passed: " + target, flush=True)


if __name__ == "__main__":
    main()
