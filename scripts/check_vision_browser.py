"""Verify image inputs, honest replay labels, controls and optional real inference."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chromium", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    credentials = json.loads(args.credentials.read_text())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, args=["--no-sandbox"],
            **({"executable_path": str(args.chromium)} if args.chromium else {}),
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors, calls = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url.rstrip("/") + "/#vision", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".vs-source")).to_contain_text("历史实测", timeout=30000)
        expect(page.locator("[data-page=vision]")).to_have_class("nav-item active")

        def settled():
            expect(page.locator("[data-v-run]")).to_be_enabled(timeout=55000)

        def live():
            with page.expect_response(lambda response: response.url.endswith("/api/vision/decide")) as pending:
                page.locator("[data-v-run]").click()
            response = pending.value
            data = response.json()
            assert response.status == 200, data
            assert data["source"] == "live"
            assert data["model"] == "strands-decider-2B-hobson-v19-vision"
            assert data["backend_total_ms"] >= 0
            calls.append(data)
            settled()
            expect(page.locator(".vs-source")).to_contain_text("实时结果")
            return data

        settled()
        page.locator("[data-v-case]").select_option("case-02")
        expect(page.locator('[data-v-answer="status"] .vs-choice')).to_contain_text("等待确认")
        expect(page.locator(".vs-metrics")).to_contain_text("采集时模型耗时")
        page.screenshot(path=str(args.output.with_name(args.output.stem + "-payment.png")))
        if args.live:
            live()
        page.locator('[data-v-group="support"]').click()
        expect(page.locator('[data-v-answer="queue"] .vs-choice')).to_contain_text("退款队列")
        settled()
        if args.live:
            live()
        page.locator('[data-v-group="receipt"]').click()
        settled()
        page.locator("[data-v-case]").select_option("case-11")
        expect(page.locator('[data-v-answer="action"] .vs-choice')).to_contain_text("接收凭证")
        expect(page.locator('[data-v-answer="action"] .vs-mismatch')).to_be_visible()
        page.locator("[data-v-variant]").select_option("reverse")
        expect(page.locator('[data-v-answer="action"] .vs-choice')).to_contain_text("补全编号和签名")
        if args.live:
            live()
        page.locator("[data-v-variant]").select_option("no_image")
        settled()
        expect(page.locator(".vs-image-overlay")).to_be_visible()
        expect(page.locator(".vs-match")).to_have_count(0)
        expect(page.locator(".vs-mismatch")).to_have_count(0)
        if args.live:
            assert not live()["request"]["image"]["sent"]
        page.locator("[data-v-variant]").select_option("blank")
        settled()
        expect(page.locator(".vs-image-wrap img")).to_have_attribute("src", "/static/vision/blank.png")
        page.locator("[data-v-upload]").set_input_files(ROOT / "validation/vision/images/case-11.png")
        settled()
        expect(page.locator("[data-v-recorded]")).to_be_disabled()
        expect(page.locator(".vs-empty")).to_be_visible()
        if args.live:
            data = live()
            assert data["case_id"] is None and data["expected"] is None
            assert data["request"]["image"]["sent"]
        else:
            page.locator("[data-v-run]").click()
            expect(page.locator(".vs-error")).to_contain_text("未配置")
            expect(page.locator(".vs-source")).to_have_count(0)
        page.locator("[data-v-case]").select_option("case-11")
        expect(page.locator(".vs-source")).to_contain_text("历史实测")
        expect(page.locator(".vs-mismatch")).to_be_visible()
        page.screenshot(path=str(args.output.with_name(args.output.stem + "-receipt.png")))
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.output.with_name(args.output.stem + "-mobile.png")), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        args.output.write_text(json.dumps({
            "url": args.url, "live_calls": calls, "browser_errors": errors,
            "replay_labeled": True, "upload_no_reference": True, "controls_verified": True,
            "mobile_no_horizontal_overflow": True,
        }, ensure_ascii=False, indent=2) + "\n")
        browser.close()
    print(json.dumps({"verified": True, "live_calls": len(calls), "output": str(args.output)}))


if __name__ == "__main__":
    main()
