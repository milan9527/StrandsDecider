"""UI regression: simulated GPU states and real sandbox replay endpoints, no model/GPU start."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(".deployment/crypto-loop-browser.json"))
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    errors, model_requests = [], []
    gpu = {
        "enabled": True,
        "can_manage": True,
        "provider": "sagemaker",
        "phase": "stopped",
        "desired": "stopped",
        "instance_type": "ml.g6.xlarge",
        "instance_id": None,
        "instance_usd_per_hour": 1.1267,
        "maximum_instance_usd_per_hour": 1.1267,
        "disk_usd_per_month": 6.4,
        "disk_retained": True,
        "idle_remaining_seconds": 1800,
        "endpoint_status": "Absent",
        "busy": False,
    }
    start_requests = []
    status_error = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "request",
            lambda r: (
                model_requests.append(r.url)
                if r.url.endswith(("/crypto/decision", "/loop/tick"))
                else None
            ),
        )

        def gpu_status(route):
            route.fulfill(
                status=503 if status_error else 200,
                json={"detail": "测试状态读取失败"} if status_error else gpu,
            )

        def start_gpu(route):
            start_requests.append(route.request.method)
            gpu.update(phase="starting", desired="running", endpoint_status="Creating")
            route.fulfill(status=202, json=gpu)

        page.route("**/api/gpu", gpu_status)
        page.route("**/api/gpu/start", start_gpu)
        page.goto(args.url + "/#crypto", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".cx-case")).to_have_count(4)
        expect(page.locator(".cx-summary")).to_contain_text("两侧选择不同")
        expect(page.locator(".cx-summary")).not_to_contain_text("不是准确率")
        expect(page.locator("#cx-gpu-notice")).to_contain_text("Decider GPU 未启动")
        expect(page.locator("#gpu-panel")).to_be_hidden()
        expect(page.locator("#gpu-open")).to_be_visible()
        expect(page.get_by_role("button", name="启动 GPU", exact=True)).to_have_count(0)
        expect(page.locator("[data-cx-start]")).to_be_in_viewport()
        expect(page.locator("[data-cx-test-kind]")).to_have_value("workflow")
        expect(page.locator("[data-cx-auto-events]")).to_have_count(0)
        page.screenshot(path="artifacts/crypto9-layout-desktop.png")
        for width in (390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            page.evaluate("window.scrollTo(0, 0)")
            expect(page.locator("[data-cx-start]")).to_be_in_viewport()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=f"artifacts/crypto9-layout-{width}.png")
        page.set_viewport_size({"width": 1600, "height": 1100})
        page.evaluate("location.hash = 'playground'")
        expect(page.locator("#gpu-open")).to_be_visible()
        page.locator("#gpu-open").click()
        expect(page.locator("#gpu-dialog")).to_be_visible()
        expect(page.get_by_role("button", name="启动 GPU", exact=True)).to_have_count(1)
        page.locator("#gpu-close").click()
        page.evaluate("location.hash = 'crypto'")
        expect(page.locator("#gpu-panel")).to_be_hidden()
        expect(page.get_by_role("button", name="启动 GPU", exact=True)).to_have_count(0)
        page.locator("[data-cx-start]").click()
        expect(page.locator("#toast")).to_contain_text("GPU 尚未就绪")
        expect(page.locator("[data-cx-start]")).to_be_enabled()
        expect(page.locator("#gpu-dialog")).to_be_visible()
        assert not model_requests
        page.locator("#gpu-close").click()
        page.locator("[data-cx-test-kind]").select_option("loop")
        page.locator("[data-cx-start]").click()
        expect(page.locator("#toast")).to_contain_text("GPU 尚未就绪")
        expect(page.locator("[data-cx-start]")).to_be_enabled()
        assert not model_requests
        page.locator("#gpu-dialog").screenshot(path="artifacts/crypto-gpu-prompt.png")
        page.locator("#gpu-start").click()
        expect(page.locator("#cx-gpu-notice")).to_contain_text("GPU 启动中")
        assert start_requests == ["POST"]  # Intercepted locally, never sent to AWS.
        gpu.update(phase="ready", endpoint_status="InService")
        page.locator("#gpu-refresh").click()
        expect(page.locator("#cx-gpu-notice")).to_contain_text("GPU 已就绪")
        status_error = True
        page.locator("#gpu-refresh").click()
        expect(page.locator("#cx-gpu-notice")).to_contain_text("状态暂不可用")
        page.locator("#gpu-close").click()
        page.locator("[data-cx-start]").click()
        expect(page.locator("#toast")).to_contain_text("无法确认 GPU 状态")
        assert not model_requests
        status_error = False
        gpu.update(phase="stopped", desired="stopped", can_manage=False)
        page.locator("#gpu-refresh").click()
        expect(page.locator("#cx-gpu-notice")).to_contain_text("请联系管理员")
        expect(page.locator("#gpu-start")).to_be_hidden()
        page.locator("#gpu-close").click()
        page.locator("[data-cx-mode='replay']").click()

        outputs = {}

        def export():
            with page.expect_download() as download:
                page.locator("[data-cx-export]").click()
            return json.loads(Path(download.value.path()).read_text())

        def complete():
            for provider in ("decider", "bedrock"):
                expect(page.locator(f"[data-cx-final='{provider}'] .cx-outcome")).to_contain_text(
                    "业务闭环已完成", timeout=180000
                )
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=180000)

        for scenario, event_count in (
            ("pending", 1),
            ("underpaid", 1),
            ("refund", 2),
            ("settlement", 1),
        ):
            page.locator(f"[data-cx-case='{scenario}']").click()
            page.locator("[data-cx-start]").click()
            complete()
            data = export()
            for provider in ("decider", "bedrock"):
                execution = data["executions"][provider]
                assert execution["loopState"]["status"] == "complete"
                assert len(execution["events"]) == event_count
                assert sum(bool(r.get("ledger_entry")) for r in execution["audit"]) == 1
                assert len(execution["decisionHistory"]) > 5
                assert all(r["source"] == "rule_replay" for r in execution["decisionHistory"])
                assert data["businessOutcomes"][provider]["complete"]
            outputs[scenario] = data
        page.locator(".cx-final-grid").first.screenshot(path="artifacts/crypto-loop-complete.png")
        page.locator('[data-cx-panel="loop-history"] > summary').click()
        page.locator(".cx-loop-history").screenshot(path="artifacts/crypto-loop-history.png")

        # Manual evidence resumes the existing run and retains all prior attempts.
        page.locator("[data-cx-case='pending']").click()
        page.locator("[data-cx-reset]").click()
        page.locator("[data-cx-auto-events]").uncheck()
        page.locator("[data-cx-start]").click()
        expect(page.locator("[data-cx-final='decider'] .cx-outcome")).to_contain_text(
            "等待外部条件"
        )
        expect(page.locator("[data-cx-start]")).to_be_enabled()
        before = export()
        page.locator('[data-cx-panel="inputs"] > summary').click()
        page.locator("[data-cx-event='confirm']").click()
        complete()
        after = export()
        for provider in ("decider", "bedrock"):
            assert (
                before["executions"][provider]["loopState"]["run_id"]
                == after["executions"][provider]["loopState"]["run_id"]
            )
            assert len(after["executions"][provider]["audit"]) > len(
                before["executions"][provider]["audit"]
            )
        outputs["manual_resume"] = after

        # A failing request pauses one provider. Resume must not repeat the other
        # provider's already completed financial action.
        page.locator("[data-cx-reset]").click()
        page.locator("[data-cx-auto-events]").check()

        def fail_execution(route):
            body = route.request.post_data_json
            if body["provider"] == "decider" and body["state"]["next_stage"] == "execute":
                route.fulfill(status=503, json={"detail": "测试闭环请求暂不可用"})
            else:
                route.continue_()

        page.route("**/api/crypto/loop/tick", fail_execution)
        page.locator("[data-cx-start]").click()
        expect(page.locator("[data-cx-final='decider']")).to_contain_text(
            "测试闭环请求暂不可用", timeout=60000
        )
        expect(page.locator("[data-cx-final='bedrock'] .cx-outcome")).to_contain_text(
            "业务闭环已完成"
        )
        expect(page.locator("[data-cx-start]")).to_be_enabled()
        page.unroute("**/api/crypto/loop/tick", fail_execution)
        completed_other = export()["executions"]["bedrock"]["loopState"]
        page.locator("[data-cx-loop-resume]").click()
        complete()
        resumed = export()
        assert resumed["executions"]["bedrock"]["loopState"] == completed_other
        assert any(r.get("error") for r in resumed["executions"]["decider"]["audit"])
        assert any(r["kind"] == "error" for r in resumed["executions"]["decider"]["timeline"])
        outputs["request_retry"] = resumed

        for width in (390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            page.locator(".cx-test-setup").screenshot(
                path=f"artifacts/crypto-loop-controls-{width}.png"
            )
        page.locator("#logout-button").click()
        expect(page.locator("#login-page")).to_be_visible()
        assert not errors, errors
        browser.close()
    args.output.write_text(
        json.dumps(
            {
                "gpu_controls": "simulated responses; no real startup",
                "model_mode": "rule_replay",
                "results": outputs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        "Passed: GPU preflight/start/unknown/non-admin, all four loops, manual resume, failure/retry, one ledger per run, history/export, mobile. No real model/GPU calls."
    )


if __name__ == "__main__":
    main()
