"""Check always-on direct inference and the visible run bar using intercepted model calls."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8012")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".deployment/direct-run-browser.json"))
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    gpu = {
        "enabled": True,
        "can_manage": True,
        "provider": "ec2",
        "phase": "ready",
        "desired": "running",
        "instance_type": "g6.xlarge",
        "instance_options": ["g6.xlarge"],
        "instance_id": "i-intercepted-test",
        "instance_usd_per_hour": 0.8048,
        "maximum_instance_usd_per_hour": 0.8048,
        "disk_usd_per_month": 6.4,
        "disk_retained": True,
        "idle_auto_stop": False,
        "idle_minutes": 0,
        "idle_remaining_seconds": None,
    }
    events, errors = [], []
    status_error, failure_status, failure_provider = False, 0, "decider"
    Path("artifacts").mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))

        def status(route):
            events.append("gpu")
            route.fulfill(
                status=503 if status_error else 200,
                json={"detail": "测试状态服务不可用"} if status_error else gpu,
            )

        def model(route):
            body = route.request.post_data_json
            provider = body.get("provider", "decider")
            events.append("model:" + provider)
            if failure_status and provider == failure_provider:
                route.fulfill(status=failure_status, json={"detail": "测试模型调用失败"})
                return
            # Exercise the UI with real replay endpoints, never pretend to benchmark a model.
            body["mode"] = "replay" if "/crypto/" in route.request.url else "example"
            response = route.fetch(post_data=json.dumps(body))
            assert response.ok, response.text()
            route.fulfill(response=response)

        page.route("**/api/gpu", status)
        page.route(
            "**/api/health",
            lambda r: r.fulfill(json={"connected": False, "message": "浏览器测试，未连接真实模型"}),
        )
        for path in ("decide", "guard", "crypto/decision", "crypto/loop/tick"):
            page.route("**/api/" + path, model)
        page.goto(args.url, wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator("#gpu-launcher-label")).to_contain_text("已就绪")
        expect(page.locator(".scenario-card")).to_have_count(16)
        expect(page.locator("#run-decision")).to_be_enabled()
        expect(page.locator("#run-decision")).to_be_in_viewport()
        expect(page.locator("#run-decision")).to_have_count(1)
        page.locator('[data-example="rag"]').click()
        expect(page.locator("#run-scenario")).to_have_text("RAG 回答依据")
        page.locator("#edit-decision").click()
        expect(page.locator("#state-input")).to_be_focused()
        expect(page.locator("#run-decision")).to_be_in_viewport()
        page.locator("#add-question").click()
        expect(page.locator("#run-question-count")).to_have_text("4 个问题")
        page.locator("#reset-example").click()
        expect(page.locator("#run-question-count")).to_have_text("3 个问题")

        # Successful calls in every module skip GPU status; the closed dialog does not poll.
        events.clear()
        for module, button, result in (
            ("playground", "#run-decision", "#results .answer-card"),
            ("guard", "#run-guard", "#guard-results .answer-card"),
        ):
            page.evaluate("(x) => location.hash = x", module)
            page.locator(f'#page-{module} [data-mode="live"]').click()
            page.locator(button).click()
            expect(page.locator(result)).to_have_count(3 if module == "playground" else 2)
            expect(page.locator(button)).to_be_enabled()
            expect(page.locator("#gpu-dialog")).to_be_hidden()
        page.evaluate("location.hash = 'crypto'")
        for kind in ("workflow", "loop", "all"):
            page.locator("[data-cx-test-kind]").select_option(kind)
            page.locator("[data-cx-start]").click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=30000)
            expect(page.locator(".cx-turn-pending")).to_have_count(0)
            expect(page.locator("#gpu-dialog")).to_be_hidden()
        page.wait_for_timeout(5500)
        assert "gpu" not in events, events
        assert events.count("model:decider") >= 13
        success_calls = len(events)

        # A Bedrock failure does not trigger Decider GPU diagnostics.
        failure_status, failure_provider = 503, "bedrock"
        events.clear()
        page.locator("[data-cx-start]").click()
        expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=30000)
        expect(page.locator(".cx-comparison")).to_contain_text("测试模型调用失败")
        assert "gpu" not in events, events
        expect(page.locator("#gpu-dialog")).to_be_hidden()

        page.evaluate("location.hash = 'playground'")
        failure_provider = "decider"
        # Validation and queue errors are shown without a GPU dialog or status lookup.
        for status_code in (422, 429):
            failure_status = status_code
            events.clear()
            page.locator("#run-decision").click()
            expect(page.locator("#results")).to_contain_text("测试模型调用失败")
            expect(page.locator("#run-decision")).to_be_enabled()
            expect(page.locator("#gpu-dialog")).to_be_hidden()
            assert events == ["model:decider"], events

        # Only an actual inference failure refreshes status and opens the recovery dialog.
        failure_status = 503
        gpu.update(phase="stopped", desired="stopped")
        events.clear()
        page.locator("#run-decision").click()
        expect(page.locator("#results")).to_contain_text("测试模型调用失败")
        expect(page.locator("#gpu-dialog")).to_be_visible()
        expect(page.locator("#gpu-dialog-context")).to_contain_text("本次模型调用失败")
        expect(page.locator("#gpu-start")).to_be_enabled()
        assert events[:2] == ["model:decider", "gpu"], events
        page.locator("#gpu-close").click()

        # Even a stale stopped/unknown management status cannot block a successful call.
        failure_status = 0
        status_error = True
        events.clear()
        page.locator("#run-decision").click()
        expect(page.locator("#results .answer-card")).to_have_count(3)
        expect(page.locator("#gpu-dialog")).to_be_hidden()
        assert events == ["model:decider"], events
        page.locator("#gpu-open").click()
        expect(page.locator("#gpu-status")).to_have_text("状态暂不可用")
        page.locator("#gpu-close").click()
        events.clear()
        page.locator("#run-decision").click()
        expect(page.locator("#results .answer-card")).to_have_count(3)
        expect(page.locator("#gpu-dialog")).to_be_hidden()
        assert events == ["model:decider"], events

        for width, height in ((1440, 900), (1024, 768), (390, 844), (320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("window.scrollTo(0, 0)")
            expect(page.locator("#run-decision")).to_be_in_viewport()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=f"artifacts/direct-run-{width}.png")
            page.locator("#state-input").scroll_into_view_if_needed()
            expect(page.locator("#run-decision")).to_be_in_viewport()
        assert not errors, errors
        page.locator("#logout-button").click()
        browser.close()
    args.output.write_text(
        json.dumps(
            {
                "model_api": "intercepted; replay data only",
                "gpu_api": "intercepted",
                "success_calls_without_gpu_lookup": success_calls,
                "checks": [
                    "workbench",
                    "guard",
                    "payment workflow/loop/decisions",
                    "no idle polling",
                    "failure-only GPU dialog",
                    "Bedrock/422/429 isolation",
                    "stale management state",
                    "visible sticky run bar",
                    "320px layout",
                ],
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print("Passed: direct calls, failure diagnostics, no idle polling, visible run controls.")


if __name__ == "__main__":
    main()
