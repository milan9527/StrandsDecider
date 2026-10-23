"""Verify the three image-model columns, controls, failures and optional live calls."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ("decider", "jev", "bedrock")


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
    catalog = json.loads((ROOT / "app/vision_assets/catalog.json").read_text())
    cases = {c["id"]: c for c in catalog["cases"]}
    errors, calls, simulated_failures = [], [], set()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, args=["--no-sandbox"],
            **({"executable_path": str(args.chromium)} if args.chromium else {}),
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def intercept(route):
            body = route.request.post_data_json
            if body.get("mode") != "live":
                return route.continue_()
            provider = body["provider"]
            if provider in simulated_failures:
                return route.fulfill(status=503, json={"detail": "合成浏览器测试：Jev 连接失败"})
            case = cases.get(body.get("case_id"), cases["case-11"])
            data = copy.deepcopy(case["recordings"]["original"]["response"])
            if provider == "jev":
                data["model"] = "jev-test-browser-fixture"
            elif provider == "bedrock":
                data["model"] = "us.openai.gpt-6.1-sol"
                data["answers"] = {
                    key: {"type": "noul", "value": value} if type(value) is bool else
                    {"type": "choice", "choice": value, "confidence": None, "probabilities": None}
                    for key, value in case["expected"].items()
                }
            fingerprint = hashlib.sha256(json.dumps({k: v for k, v in body.items() if k != "provider"}).encode()).hexdigest()
            route.fulfill(json={
                **data, "source": "live", "provider": provider, "captured_at": None,
                "case_id": body.get("case_id"), "task": body["task"], "variant": body["variant"],
                "expected": case["expected"] if body.get("case_id") and body["variant"] in ("original", "reverse") else None,
                "model_ms": 100 if provider == "decider" else None,
                "backend_total_ms": {"decider": 120, "jev": 250, "bedrock": 900}[provider],
                "input_fingerprint": fingerprint,
                "request": {**case["request"], "image": {"sent": body["variant"] != "no_image"}},
            })

        if not args.live:
            page.route("**/api/vision/decide", intercept)

        def observe(response):
            if response.url.endswith("/api/vision/decide") and response.request.post_data_json.get("mode") == "live":
                calls.append({"status": response.status, "body": response.json(),
                              "provider": response.request.post_data_json["provider"]})

        page.on("response", observe)
        page.goto(args.url.rstrip("/") + "/#vision", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        decider = page.locator('[data-v-provider="decider"]')
        expect(decider.locator(".vs-source")).to_contain_text("历史实测", timeout=30000)
        expect(page.locator("[data-page=vision]")).to_have_class("nav-item active")
        expect(page.locator(".vs-model-card")).to_have_count(3)
        expect(page.locator('[data-v-provider="jev"]')).to_contain_text("没有历史实测")
        page.locator("[data-v-zoom]").click()
        expect(page.locator(".vs-image-dialog")).to_be_visible()
        page.locator(".vs-image-dialog button").click()
        expect(page.locator(".vs-image-dialog")).to_have_count(0)

        def settled():
            expect(page.locator("[data-v-run]")).to_be_enabled(timeout=55000)

        def compare():
            before = len(calls)
            page.locator("[data-v-run]").click()
            expect(page.locator(".vs-source.live")).to_have_count(3, timeout=55000)
            settled()
            batch = calls[before:]
            assert len(batch) == 3 and all(c["status"] == 200 for c in batch), batch
            assert {c["provider"] for c in batch} == set(PROVIDERS)
            assert len({c["body"]["input_fingerprint"] for c in batch}) == 1
            expect(page.locator("[data-v-summary]")).to_contain_text("3/3 返回成功")
            for call in batch:
                provider = call["provider"]
                data = call["body"]
                assert data["source"] == "live" and data["backend_total_ms"] >= 0
                if provider == "decider":
                    assert data["model"].endswith("-vision")
                elif provider == "bedrock":
                    assert data["model"] == "us.openai.gpt-6.1-sol"
                    assert all(a.get("probabilities") is None and a.get("noul") is None for a in data["answers"].values())
            return batch

        settled()
        page.locator("[data-v-case]").select_option("case-02")
        expect(decider.locator('[data-v-answer="status"]')).to_contain_text("等待确认")
        settled()
        compare()
        page.screenshot(path=str(args.output.with_name(args.output.stem + "-payment.png")), full_page=True)
        page.locator('[data-v-group="support"]').click()
        settled()
        compare()
        page.locator('[data-v-group="receipt"]').click()
        settled()
        page.locator("[data-v-case]").select_option("case-11")
        expect(decider.locator('[data-v-answer="action"] .vs-mismatch')).to_be_visible()
        settled()
        compare()
        page.screenshot(path=str(args.output.with_name(args.output.stem + "-receipt.png")), full_page=True)
        page.locator("[data-v-variant]").select_option("reverse")
        settled()
        expect(decider.locator('[data-v-answer="action"]')).to_contain_text("补全编号和签名")
        page.locator("[data-v-variant]").select_option("no_image")
        settled()
        expect(page.locator(".vs-image-overlay")).to_be_visible()
        batch = compare()
        assert all(not c["body"]["request"]["image"]["sent"] and c["body"]["expected"] is None for c in batch)
        expect(page.locator(".vs-match")).to_have_count(0)
        expect(page.locator(".vs-mismatch")).to_have_count(0)
        page.locator("[data-v-variant]").select_option("blank")
        settled()
        expect(page.locator(".vs-image-wrap img")).to_have_attribute("src", "/static/vision/blank.png")
        page.locator("[data-v-upload]").set_input_files(ROOT / "validation/vision/images/case-11.png")
        settled()
        expect(page.locator("[data-v-recorded]")).to_be_disabled()
        batch = compare()
        assert all(c["body"]["case_id"] is None and c["body"]["expected"] is None for c in batch)
        expect(page.locator(".vs-hint").filter(has_text="三模型共用 448 × 448 PNG")).to_be_visible()
        if not args.live:
            simulated_failures.add("jev")
            page.locator("[data-v-run]").click()
            expect(page.locator('[data-v-provider="jev"] .vs-error')).to_contain_text("连接失败")
            settled()
            expect(page.locator(".vs-source.live")).to_have_count(2)
            expect(page.locator("[data-v-summary]")).to_contain_text("1 个模型失败")
            expect(page.locator("[data-v-summary]")).not_to_contain_text("选择相同")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.output.with_name(args.output.stem + "-mobile.png")), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        args.output.write_text(json.dumps({
            "url": args.url, "mode": "live_integration" if args.live else "synthetic_browser_regression",
            "calls": calls, "browser_errors": errors, "historical_not_compared": True,
            "upload_no_reference": True, "mobile_no_horizontal_overflow": True,
        }, ensure_ascii=False, indent=2) + "\n")
        browser.close()
    print(json.dumps({"verified": True, "calls": len(calls), "mode": "live" if args.live else "synthetic"}))


if __name__ == "__main__":
    main()
