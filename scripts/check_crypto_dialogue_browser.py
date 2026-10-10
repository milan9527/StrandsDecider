"""Verify visible per-round inputs/outputs using sandbox replay, including history and failures."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path(".deployment/crypto-dialogue-browser.json")
    )
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    errors = []
    Path("artifacts").mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.url + "/#crypto", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".cx-dialogues")).to_be_visible()
        expect(page.locator(".cx-conversation")).to_be_visible()
        assert not page.locator(".cx-dialogues").evaluate("(el) => !!el.closest('details')")
        assert not page.locator(".cx-conversation").evaluate("(el) => !!el.closest('details')")
        expect(page.locator(".cx-dialogue-empty")).to_contain_text("客户输入")
        expect(page.locator(".cx-dialogue-heading")).to_be_in_viewport()
        page.locator('[data-cx-mode="replay"]').click()

        def run(kind="workflow"):
            page.locator("[data-cx-test-kind]").select_option(kind)
            page.locator("[data-cx-start]").click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=180000)
            expect(page.locator(".cx-turn-pending")).to_have_count(0)

        def export():
            with page.expect_download() as download:
                page.locator("[data-cx-export]").click()
            return json.loads(Path(download.value.path()).read_text())

        run()
        fixed = export()
        assert len(fixed["dialogues"]) == 5
        expect(page.locator(".cx-turn")).to_have_count(5)
        expect(page.locator("[data-cx-dialogue-output]")).to_have_count(10)
        original_message = fixed["snapshot"]["message"]
        for row in fixed["dialogues"]:
            a, b = row["sides"]["decider"], row["sides"]["bedrock"]
            assert a["request"]["snapshot"] == b["request"]["snapshot"]
            for side in (a, b):
                assert side["request"]["snapshot"]["confirmations"] == 3
                assert side["result"]["source"] == "rule_replay"
                assert not side["pending"] and side["elapsedMs"] >= 0
                assert side["executions"][-1]["stage"] == side["request"]["stage"]
        expect(page.locator(".cx-dialogue-feed")).to_contain_text("客服回复（模板）")
        first_turn = page.locator('[data-cx-dialogue-turn="1"]')
        first_turn.scroll_into_view_if_needed()
        expect(first_turn).to_contain_text(original_message)
        expect(first_turn).to_contain_text("回放输出")
        expect(first_turn).to_contain_text("实际执行")
        first_turn.locator("details").first.locator("summary").click()
        expect(first_turn.locator("pre").first).to_contain_text('"snapshot"')
        first_turn.locator("details").first.locator("summary").click()
        page.screenshot(path="artifacts/crypto10-dialogue-desktop.png")

        # Old inputs are immutable when evidence or customer text changes.
        page.locator('[data-cx-event="confirm"]').click()
        expect(page.locator('[data-cx-event-notice="confirm"]')).to_contain_text("3/12 → 12/12")
        message = '请核实到账 <img src=x onerror="window.__cxXss=1">'
        page.locator("#cx-message").fill(message)
        page.locator("[data-cx-save-message]").click()
        run()
        changed = export()
        assert len(changed["dialogues"]) == 10
        for row in changed["dialogues"]:
            for side in row["sides"].values():
                s = side["request"]["snapshot"]
                assert s["message"] == (original_message if row["run"] == 1 else message)
                assert s["confirmations"] == (3 if row["run"] == 1 else 12)
        assert page.evaluate("window.__cxXss") is None
        expect(page.locator(".cx-dialogues img")).to_have_count(0)
        page.locator("[data-cx-dialogue-run]").select_option("1")
        expect(page.locator(".cx-dialogue-feed")).to_contain_text(original_message)
        expect(page.locator(".cx-dialogue-feed")).not_to_contain_text(message)
        page.locator("[data-cx-dialogue-run]").select_option("2")
        expect(page.locator(".cx-dialogue-feed")).to_contain_text(message)
        for width in (1024, 390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            page.locator(".cx-dialogue-heading").evaluate(
                "(el) => el.scrollIntoView({block: 'start'})"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator(".cx-dialogue-feed").evaluate(
                "(el) => el.scrollWidth <= el.clientWidth"
            )
            page.screenshot(path=f"artifacts/crypto10-dialogue-{width}.png")
        page.set_viewport_size({"width": 1600, "height": 1100})

        # Capture every loop tick, including simulator-only outputs and rejudgment feedback.
        page.locator('[data-cx-case="refund"]').click()
        run("loop")
        loop = export()
        for provider in ("decider", "bedrock"):
            sides = [row["sides"][provider] for row in loop["dialogues"]]
            decisions = [s for s in sides if s.get("result")]
            events = [s for s in sides if s["response"].get("event")]
            assert len(decisions) == loop["executions"][provider]["loopState"]["decisions"]
            assert len(events) == 2
            assert any(s["request"]["state"].get("feedback") for s in decisions)
            assert len(decisions) > 5
            assert decisions[-1]["response"]["state"]["status"] == "complete"
            for before, after in zip(sides, sides[1:], strict=False):
                assert after["request"]["state"] == before["response"]["state"]
        expect(page.locator(".cx-dialogue-feed")).to_contain_text("模拟事件输出 · 未调用模型")
        expect(page.locator(".cx-dialogue-feed")).to_contain_text("上轮反馈")
        expect(page.locator(".cx-dialogue-feed")).to_contain_text("业务闭环完成")
        page.locator(".cx-dialogue-heading").scroll_into_view_if_needed()
        page.screenshot(path="artifacts/crypto10-dialogue-loop.png")

        # A failed decision retains its input; resuming appends a new round.
        page.locator('[data-cx-case="pending"]').click()
        failed = False

        def fail_once(route):
            nonlocal failed
            if not failed and route.request.post_data_json["provider"] == "decider":
                failed = True
                route.fulfill(status=503, json={"detail": "对话记录测试：本轮调用失败"})
            else:
                route.continue_()

        page.route("**/api/crypto/loop/tick", fail_once)
        run("loop")
        expect(page.locator(".cx-dialogue-feed")).to_contain_text("对话记录测试：本轮调用失败")
        before_resume = export()
        latest_run = before_resume["dialogueRun"]
        failed_side = next(row for row in before_resume["dialogues"] if row["run"] == latest_run)[
            "sides"
        ]["decider"]
        assert failed_side["request"]["state"]["snapshot"]["message"] == message
        assert failed_side["error"] and not failed_side["pending"]
        page.locator("[data-cx-loop-resume]").click()
        expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=180000)
        resumed = export()
        recent = [r for r in resumed["dialogues"] if r["run"] == latest_run]
        assert recent[0]["sides"]["decider"]["error"] == failed_side["error"]
        assert recent[1]["sides"]["decider"]["result"]["source"] == "rule_replay"
        assert resumed["executions"]["decider"]["loopState"]["status"] == "complete"
        page.unroute("**/api/crypto/loop/tick", fail_once)
        page.locator("[data-cx-reset]").click()
        expect(page.locator(".cx-turn")).to_have_count(0)
        expect(page.locator(".cx-dialogue-empty")).to_be_visible()
        page.locator("#logout-button").click()
        expect(page.locator("#login-page")).to_be_visible()
        assert not errors, errors
        browser.close()
    args.output.write_text(
        json.dumps(
            {
                "mode": "rule_replay",
                "fixed_rounds": 5,
                "loop_rounds": len(loop["dialogues"]),
                "history_and_failure_resume": True,
                "browser_errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        "Passed: visible inputs/outputs, actual execution, history, loop feedback/events, errors/resume, export, escaping, mobile."
    )


if __name__ == "__main__":
    main()
