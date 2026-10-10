"""Verify shared GPU dialog with intercepted GPU/model APIs; never start real resources."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(".deployment/gpu-dialog-browser.json"))
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    gpu = {
        "enabled": True,
        "can_manage": True,
        "provider": "sagemaker",
        "phase": "stopped",
        "desired": "stopped",
        "instance_type": "ml.g6.xlarge",
        "instance_usd_per_hour": 1.1267,
        "maximum_instance_usd_per_hour": 1.1267,
        "disk_usd_per_month": 6.4,
        "disk_retained": True,
        "idle_remaining_seconds": 1800,
        "endpoint_status": "Absent",
    }
    status_error, start_error = False, False
    errors, starts, stops, inference = [], [], [], []
    Path("artifacts").mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def status(route):
            route.fulfill(
                status=503 if status_error else 200,
                json={"detail": "测试状态读取失败"} if status_error else gpu,
            )

        def start(route):
            starts.append(route.request.method)
            if start_error:
                route.fulfill(status=503, json={"detail": "测试启动失败，请重试"})
            else:
                gpu.update(phase="starting", desired="running", endpoint_status="Creating")
                route.fulfill(status=202, json=gpu)

        def stop(route):
            stops.append(route.request.method)
            gpu.update(phase="stopping", desired="stopped")
            route.fulfill(status=202, json=gpu)

        def model(route):
            inference.append(route.request.url)
            route.fulfill(status=503, json={"detail": "测试已截获推理请求，未调用真实模型"})

        page.route("**/api/gpu", status)
        page.route("**/api/gpu/start", start)
        page.route("**/api/gpu/stop", stop)
        for path in ("decide", "guard", "crypto/decision", "crypto/loop/tick"):
            page.route(f"**/api/{path}", model)
        page.goto(args.url, wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".scenario-card")).to_have_count(16)

        # Every module has the same launcher and exactly one set of actual controls.
        for module in ("playground", "guard", "crypto", "history", "about"):
            page.evaluate("(module) => location.hash = module", module)
            expect(page.locator(f"#page-{module}")).to_be_visible()
            expect(page.locator("#gpu-open")).to_be_visible()
            expect(page.locator("#gpu-dialog")).to_be_hidden()
            page.locator("#gpu-open").click()
            expect(page.get_by_role("dialog", name="GPU 管理")).to_be_visible()
            expect(page.get_by_role("button", name="启动 GPU", exact=True)).to_have_count(1)
            expect(page.locator("#gpu-start")).to_be_enabled()
            page.keyboard.press("Escape")
            expect(page.locator("#gpu-dialog")).to_be_hidden()
            expect(page.locator("#gpu-open")).to_be_focused()
        assert starts == []

        # No inference request escapes preflight in any of the three live modules.
        for module, trigger in (("playground", "#run-decision"), ("guard", "#run-guard")):
            page.evaluate("(module) => location.hash = module", module)
            page.locator(f'#page-{module} [data-mode="live"]').click()
            page.locator(trigger).click()
            expect(page.locator("#gpu-dialog")).to_be_visible()
            expect(page.locator(trigger)).to_be_enabled()
            page.locator("#gpu-return").click()
        page.evaluate("location.hash = 'crypto'")
        for kind in ("workflow", "loop", "all"):
            page.locator("[data-cx-test-kind]").select_option(kind)
            page.locator("[data-cx-start]").click()
            expect(page.locator("#gpu-dialog")).to_be_visible()
            expect(page.locator("[data-cx-start]")).to_be_enabled()
            page.keyboard.press("Control+Enter")
            page.locator("#gpu-close").click()
        assert not inference and not starts

        # Start errors stay visible in the dialog; retry cannot submit twice.
        page.locator("[data-cx-gpu-open]").click()
        start_error = True
        page.locator("#gpu-start").click()
        expect(page.locator("#gpu-action-error")).to_contain_text("测试启动失败")
        expect(page.locator("#gpu-start")).to_be_enabled()
        start_error = False
        page.locator("#gpu-start").evaluate("(el) => { el.click(); el.click(); }")
        expect(page.locator("#gpu-status")).to_have_text("启动中")
        expect(page.locator("#gpu-start")).to_be_disabled()
        expect(page.locator("#gpu-action-error")).to_be_hidden()
        assert starts == ["POST", "POST"]
        gpu.update(phase="ready", endpoint_status="InService")
        # Polling updates an open dialog, without auto-running the interrupted task.
        expect(page.locator("#gpu-status")).to_have_text("GPU 就绪", timeout=15000)
        assert not inference
        page.locator("#gpu-return").click()

        for module, trigger, result in (
            ("playground", "#run-decision", "#results"),
            ("guard", "#run-guard", "#guard-results"),
        ):
            page.evaluate("(module) => location.hash = module", module)
            page.locator(trigger).click()
            expect(page.locator(result)).to_contain_text("测试已截获推理请求")
            expect(page.locator("#gpu-dialog")).to_be_hidden()
        assert len(inference) == 2

        # A model error after a successful preflight still refreshes GPU state.
        page.evaluate("location.hash = 'crypto'")
        for kind, count in (("workflow", 10), ("loop", 2)):
            before = len(inference)
            page.locator("[data-cx-test-kind]").select_option(kind)
            page.locator("[data-cx-start]").click()
            expect(page.locator("[data-cx-compare='decider-intake']")).to_contain_text(
                "测试已截获推理请求"
            )
            expect(page.locator("[data-cx-start]")).to_be_enabled()
            assert len(inference) == before + count
            expect(page.locator("#gpu-dialog")).to_be_hidden()
        expected_inference = len(inference)
        page.evaluate("location.hash = 'guard'")

        # Stopping and unknown states cannot pass a stale ready check.
        page.locator("#gpu-open").click()
        page.locator("#gpu-stop").click()
        expect(page.locator("#gpu-status")).to_have_text("停止中")
        page.locator("#gpu-return").click()
        page.locator("#run-guard").click()
        expect(page.locator("#gpu-dialog")).to_be_visible()
        assert len(inference) == expected_inference and stops == ["POST"]
        gpu.update(phase="ready", desired="running")
        status_error = True
        page.locator("#gpu-refresh").click()
        expect(page.locator("#gpu-status")).to_have_text("状态暂不可用")
        expect(page.locator("#gpu-start")).to_be_disabled()
        expect(page.locator("#gpu-stop")).to_be_disabled()
        page.locator("#gpu-close").click()
        page.locator("#run-guard").click()
        expect(page.locator("#gpu-dialog")).to_be_visible()
        expect(page.locator("#gpu-message")).to_contain_text("无法确认 GPU 状态")
        assert len(inference) == expected_inference

        # Initial status failures also show a usable refresh dialog.
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#gpu-open")).to_contain_text("状态未知")
        page.locator("#gpu-open").click()
        expect(page.locator("#gpu-message")).to_contain_text("测试状态读取失败")
        status_error = False
        gpu.update(phase="stopped", desired="stopped", can_manage=False)
        page.locator("#gpu-refresh").click()
        expect(page.locator("#gpu-access-hint")).to_be_visible()
        expect(page.locator("#gpu-start")).to_be_hidden()
        expect(page.locator("#gpu-stop")).to_be_hidden()

        gpu.update(can_manage=True)
        page.locator("#gpu-refresh").click()
        expect(page.locator("#gpu-start")).to_be_enabled()
        page.screenshot(path="artifacts/gpu-dialog-desktop.png")
        for width in (1024, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 740})
            expect(page.locator("#gpu-start")).to_be_in_viewport()
            expect(page.locator("#gpu-return")).to_be_in_viewport()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator("#gpu-dialog").evaluate("(el) => el.scrollWidth <= el.clientWidth")
            page.screenshot(path=f"artifacts/gpu-dialog-{width}.png")
            page.locator("#gpu-close").click()
            expect(page.locator("#gpu-open")).to_be_in_viewport()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#gpu-open").click()

        # A local environment without GPU management can use its configured model.
        gpu.update(enabled=False, can_manage=False)
        page.locator("#gpu-refresh").click()
        expect(page.locator("#gpu-open")).to_be_hidden()
        page.locator("#gpu-close").click()
        page.locator('#page-guard [data-mode="live"]').click()
        page.locator("#run-guard").click()
        expect(page.locator("#guard-results")).to_contain_text("测试已截获推理请求")
        assert len(inference) == expected_inference + 1
        page.locator("#logout-button").click()
        expect(page.locator("#login-page")).to_be_visible()
        expect(page.locator("#gpu-dialog")).to_be_hidden()
        assert not errors, errors
        browser.close()
    args.output.write_text(
        json.dumps(
            {"modules": 5, "gpu_api": "intercepted", "model_api": "intercepted", "errors": errors},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        "Passed: shared dialog, all modules, preflight, start/retry/poll/stop, errors, access, mobile."
    )


if __name__ == "__main__":
    main()
