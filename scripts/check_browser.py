"""Exercise the browser UI against a running demo; optionally include real inference."""

import argparse
import json
import os
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--live", action="store_true", help="Also make a real model request")
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        launch = {"headless": True}
        if os.getenv("CHROMIUM_PATH"):
            launch["executable_path"] = os.environ["CHROMIUM_PATH"]
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="domcontentloaded")
        expect(page.locator("#login-page")).to_be_visible()
        expect(page.locator(".shell")).to_be_hidden()
        expect(page.locator("#login-submit")).to_be_enabled()
        assert page.request.get(args.url + "/api/examples").status == 401
        page.screenshot(path=str(artifacts / "login-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(artifacts / "login-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1050})
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill("incorrect-password")
        page.locator("#toggle-password").click()
        expect(page.locator("#login-password")).to_have_attribute("type", "text")
        page.locator("#toggle-password").click()
        page.locator("#login-submit").click()
        expect(page.locator("#login-error")).to_contain_text("用户名或密码不正确")
        expect(page.locator(".shell")).to_be_hidden()
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".scenario-card")).to_have_count(12)
        expect(page.locator("#login-page")).to_be_hidden()
        expect(page.locator("#account-name")).to_have_text(credentials["username"])
        assert "decider_session" not in page.evaluate("document.cookie")
        expect(page.locator("#questions .question-card")).to_have_count(3)

        catalog = page.request.get(args.url + "/api/examples").json()
        assert {item["id"] for item in catalog} == {
            "support",
            "tools",
            "sentiment",
            "language",
            "refund",
            "leads",
            "moderation",
            "invoice",
            "incident",
            "rag",
            "approval",
            "summary",
        }
        page.locator('[data-category="Agent 流程"]').click()
        expect(page.locator(".scenario-card")).to_have_count(3)
        page.locator("#scenario-search").fill("RAG")
        expect(page.locator(".scenario-card")).to_have_count(1)
        page.locator('[data-example="rag"]').click()
        expect(page.locator("#selected-scenario-title")).to_have_text("RAG 回答依据")
        expect(page.locator("#scenario-suggestion")).to_contain_text("酒店")
        page.locator("#state-input").fill("User-edited context must survive filtering.")
        page.locator("#scenario-search").fill("not-a-scenario-<img>")
        expect(page.locator(".scenario-card")).to_have_count(0)
        expect(page.locator(".scenario-empty")).to_contain_text("没有匹配的场景")
        page.locator("#clear-scenario-filters").click()
        expect(page.locator(".scenario-card")).to_have_count(12)
        expect(page.locator("#state-input")).to_have_value(
            "User-edited context must survive filtering."
        )
        page.locator("#scenario-search").fill("ECS")
        expect(page.locator(".scenario-card")).to_have_count(1)
        expect(page.locator('[data-example="incident"]')).to_be_visible()
        page.locator("#scenario-search").fill("")
        expect(page.locator(".scenario-card")).to_have_count(12)
        page.locator("#reset-example").click()
        page.screenshot(path=str(artifacts / "scenarios-desktop.png"), full_page=True)

        for example in catalog:
            count = len(example["questions"])
            page.locator(f'[data-example="{example["id"]}"]').click()
            expect(page.locator("#selected-scenario-title")).to_have_text(example["title"])
            expect(page.locator("#scenario-description")).to_have_text(example["description"])
            expect(page.locator("#questions .question-card")).to_have_count(count)
            page.locator("#run-decision").click()
            expect(page.locator("#results .answer-card")).to_have_count(count)
            expect(page.locator("#results .source-banner")).to_contain_text("非模型推理")
            expect(page.locator("#results .answer-duration")).to_have_count(count)
            assert all(
                "未推理" in text
                for text in page.locator("#results .answer-duration").all_text_contents()
            )
            expect(page.locator("#results .total-duration strong")).to_have_text(
                re.compile(r"\d.*(?:ms|s)$")
            )

        page.locator('[data-result-tab="json"]').click()
        expect(page.locator("#results pre")).to_contain_text('"source": "example"')
        page.locator('[data-result-tab="request"]').click()
        expect(page.locator("#results pre")).to_contain_text("--data-binary @request.json")
        page.locator('[data-result-tab="visual"]').click()

        page.locator("#state-input").fill('<img src=x onerror="window.__xss=true"> custom input')
        page.locator("#run-decision").click()
        expect(page.locator("#results .result-error")).to_contain_text("只支持原始预设")
        expect(page.locator(".running-elapsed")).to_have_count(0)
        assert page.evaluate("window.__xss === undefined")
        page.locator('[data-example="support"]').click()
        page.locator("#add-question").click()
        expect(page.locator("#questions .question-card")).to_have_count(4)
        page.locator(".question-card").last.locator("select").select_option("score")
        expect(page.locator(".question-card").last.locator(".option-chip")).to_have_count(3)
        page.locator(".question-card").last.locator("[data-remove]").click()
        expect(page.locator("#questions .question-card")).to_have_count(3)
        page.locator("#reset-example").click()

        if args.live:
            page.locator('[data-example="rag"]').click()
            page.locator('#page-playground [data-mode="live"]').click()
            with page.expect_response("**/api/decide", timeout=190000) as decision_response:
                page.locator("#run-decision").click()
                expect(page.locator("#results .running-elapsed")).to_be_visible()
            expect(page.locator("#results .source-banner.live")).to_be_visible(timeout=190000)
            expect(page.locator("#results .answer-card")).to_have_count(3)
            expect(page.locator("#results")).to_contain_text("模型处理耗时")
            measured = decision_response.value.json()["timings"]
            assert measured["execution"] == "individual"
            assert set(measured["decisions_ms"]) == {
                "can_answer",
                "next_action",
                "evidence_quality",
            }
            assert all(value > 0 for value in measured["decisions_ms"].values())
            assert measured["backend_total_ms"] >= sum(measured["decisions_ms"].values()) - 0.01
            for badge in page.locator("#results .answer-duration").all_text_contents():
                assert re.fullmatch(r"耗时 \d+\.\d+ (?:ms|s)", badge), badge
            expect(page.locator("#results .total-duration strong")).to_have_text(
                re.compile(r"\d.*(?:ms|s)$")
            )
            expect(page.locator(".running-elapsed")).to_have_count(0)
            page.locator('[data-result-tab="json"]').click()
            displayed = json.loads(page.locator("#results pre").inner_text())
            assert displayed["timings"]["client_total_ms"] >= measured["backend_total_ms"] - 5
            page.locator('[data-result-tab="visual"]').click()
            page.screenshot(path=str(artifacts / "timing-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#results").screenshot(path=str(artifacts / "timing-results-mobile.png"))
            page.set_viewport_size({"width": 1440, "height": 1050})
            page.locator('#page-playground [data-mode="example"]').click()

        page.locator('nav [data-page="guard"]').click()
        page.locator("#run-guard").click()
        expect(page.locator(".guard-verdict h3")).to_have_text("Guide")
        page.locator('[data-guard-preset="grounded"]').click()
        page.locator("#run-guard").click()
        expect(page.locator(".guard-verdict h3")).to_have_text("Proceed")
        page.locator("#guard-threshold").focus()
        for _ in range(5):
            page.keyboard.press("ArrowRight")
        expect(page.locator("#threshold-value")).to_have_text("0.70")
        expect(page.locator(".guard-verdict")).to_have_count(0)

        if args.live:
            page.locator('#page-guard [data-mode="live"]').click()
            page.locator("#run-guard").click()
            expect(page.locator("#guard-results .running-elapsed")).to_be_visible()
            expect(page.locator("#guard-results .source-banner.live")).to_be_visible(timeout=190000)
            expect(page.locator("#guard-results .answer-duration")).to_have_count(2)
            for badge in page.locator("#guard-results .answer-duration").all_text_contents():
                assert re.fullmatch(r"耗时 \d+\.\d+ (?:ms|s)", badge), badge
            expect(page.locator("#guard-results .total-duration strong")).to_have_text(
                re.compile(r"\d.*(?:ms|s)$")
            )
            page.locator('#page-guard [data-mode="example"]').click()

        page.locator('nav [data-page="history"]').click()
        history_count = len(catalog) + (4 if args.live else 2)
        expect(page.locator(".history-row")).to_have_count(history_count)
        page.reload(wait_until="domcontentloaded")
        expect(page.locator(".history-row")).to_have_count(history_count)
        expect(page.locator(".history-duration").first).to_contain_text("总时间")
        page.locator(".history-row summary").first.click()
        expect(page.locator(".history-row").first.locator(".history-timings")).to_be_visible()
        with page.expect_download() as download_info:
            page.locator("[data-export]").first.click()
        download = download_info.value
        data = json.loads(Path(download.path()).read_text())
        assert data["result"]["source"] in ("live", "example")
        assert data["result"]["timings"]["client_total_ms"] > 0
        if args.live:
            assert len(data["result"]["timings"]["decisions_ms"]) == 2
        page.locator("#clear-history").click()
        expect(page.locator(".history-empty")).to_be_visible()

        page.locator('nav [data-page="playground"]').click()
        expect(page.locator("#page-playground")).to_be_visible()
        expect(page.locator("#questions .question-card")).to_have_count(3)
        page.locator("#state-input").focus()
        page.keyboard.press("Control+Enter")
        expect(page.locator("#results .answer-card")).to_have_count(3)
        expect(page.locator("#toast")).to_be_hidden()
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(artifacts / "desktop.png"), full_page=True, animations="disabled")

        page.set_viewport_size({"width": 390, "height": 844})
        for name in ("playground", "guard", "history", "about"):
            page.locator(f'nav [data-page="{name}"]').click()
            expect(page.locator(f"#page-{name}")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
        page.locator('nav [data-page="playground"]').click()
        expect(page.locator("#page-playground")).to_be_visible()
        expect(page.locator('nav [data-page="playground"]')).to_have_attribute(
            "aria-current", "page"
        )
        page.screenshot(path=str(artifacts / "mobile.png"), full_page=True, animations="disabled")
        page.locator('[data-category="Agent 流程"]').click()
        page.locator("#scenario-search").fill("RAG")
        expect(page.locator(".scenario-card")).to_have_count(1)
        page.locator('[data-example="rag"]').click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(artifacts / "scenarios-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 320, "height": 740})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#logout-button").click()
        expect(page.locator("#login-page")).to_be_visible()
        expect(page.locator(".shell")).to_be_hidden()
        assert page.request.get(args.url + "/api/examples").status == 401
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#login-submit")).to_be_enabled()
        expect(page.locator(".shell")).to_be_hidden()
        assert not errors, errors
        browser.close()
    print(
        "Browser checks passed: login, 12 scenarios, category/search filters, scenario guides, editing, errors, guard, timing, history, export, mobile, logout."
    )
    if args.live:
        print("Real model inference through the browser passed.")
    print(f"Screenshots: {artifacts / 'desktop.png'}, {artifacts / 'mobile.png'}")


if __name__ == "__main__":
    main()
