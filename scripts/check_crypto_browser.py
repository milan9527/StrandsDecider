"""Verify the payment sandbox, including a real optional GPT-6.1 / CUDA comparison."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".deployment/crypto-browser.json"))
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    Path("artifacts").mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.url + "/#crypto", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".cx-case")).to_have_count(4)
        expect(page.locator(".cx-lane")).to_have_count(2)
        expect(page.locator(".cx-lane.bedrock")).to_contain_text("GPT-6.1 Sol")
        expect(page.locator(".cx-conversation .cx-events")).to_contain_text("推进模拟交易")
        page.locator('[data-cx-panel="inputs"] > summary').click()
        page.locator('[data-cx-panel="diagnostics"] > summary').click()
        page.locator(".cx-workspace").screenshot(path="artifacts/crypto-workspace-desktop.png")

        def run(mode="replay", workflow=False):
            page.locator(f'[data-cx-mode="{mode}"]').click()
            page.locator("[data-cx-test-kind]").select_option("workflow" if workflow else "all")
            page.locator("[data-cx-start]").click()
            for provider in ["decider", "bedrock"]:
                expect(page.locator(f".cx-lane.{provider} .cx-model-count")).to_have_text(
                    "5/5", timeout=180000
                )
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=180000)
            assert page.locator(".cx-model-error").count() == 0
            for panel in ("execution", "outcome-decider", "outcome-bedrock"):
                details = page.locator(f'[data-cx-panel="{panel}"]')
                if details.count() and details.get_attribute("open") is None:
                    details.locator(":scope > summary").click()

        def apply(provider="decider"):
            button = page.locator(f'[data-cx-apply="{provider}"]')
            if button.is_enabled():
                button.click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=30000)

        run()
        expect(page.locator(".cx-summary-note")).to_contain_text("规则回放")
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("尚未执行")
        expect(page.locator('[data-cx-result="decider-verify"]')).to_contain_text(
            "已获得建议，尚未执行"
        )
        apply()
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("持续跟进")
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_have_class(
            "cx-outcome pending"
        )
        expect(page.locator('[data-cx-final="decider"] .cx-blockers')).to_contain_text("3/12")
        expect(page.locator('[data-cx-final="decider"] [data-cx-funds]')).to_contain_text("未落实")
        expect(page.locator(".cx-bubble.agent")).to_contain_text("3/12")
        assert page.locator(".cx-ledger").count() == 0

        # Reproduce the original 2/5 interruption with a conservative REPLAY
        # approval choice: it must now be retained and finish all five steps.
        def conservative_replay(route):
            response = route.fetch()
            data = response.json()
            body = route.request.post_data_json
            if body["provider"] == "decider" and body["stage"] == "approve":
                data.update(choice="await_approval", label="等待人工审批", matches_reference=False)
            route.fulfill(response=response, json=data)

        page.route("**/api/crypto/decision", conservative_replay)
        run(workflow=True)
        expect(page.locator('[data-cx-final="decider"]')).to_contain_text("已处理 5/5 步")
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("持续跟进")
        expect(page.locator('[data-cx-result="decider-approve"]')).to_contain_text("等待人工审批")
        expect(page.locator('[data-cx-result="decider-approve"] .cx-step-output')).to_contain_text(
            "等待人工审批"
        )
        expect(page.locator('[data-cx-result="decider-close"] .cx-step-output')).to_contain_text(
            "客服回复"
        )
        page.locator(".cx-execution-results").screenshot(
            path="artifacts/crypto-flexible-approval-desktop.png"
        )
        page.unroute("**/api/crypto/decision", conservative_replay)
        page.locator('[data-cx-event="confirm"]').click()
        expect(page.locator(".cx-lane.decider .cx-model-count")).to_have_text("0/5")
        notice = page.locator('[data-cx-event-notice="confirm"]')
        expect(notice).to_be_visible()
        expect(notice).to_contain_text("3/12 → 12/12")
        expect(notice).to_contain_text("开始对比")
        expect(page.locator(".cx-bubble.agent").filter(has_text="3/12").first).to_contain_text(
            "历史记录"
        )
        page.locator(".cx-conversation").screenshot(
            path="artifacts/crypto-conversation-event-desktop.png"
        )
        # With all external payment evidence satisfied, a wrong approval choice
        # must visibly block only that provider's funds, even though both process 5/5.
        page.route("**/api/crypto/decision", conservative_replay)
        run(workflow=True)
        expect(page.locator('[data-cx-final="decider"]')).to_contain_text("已处理 5/5 步")
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("业务未完成")
        expect(page.locator('[data-cx-final="decider"] .cx-blockers')).to_contain_text(
            "待复核状态尚未解除"
        )
        expect(page.locator('[data-cx-final="decider"] [data-cx-funds]')).to_contain_text("未落实")
        expect(
            page.locator('[data-cx-result="decider-execute"] .cx-execution-badge')
        ).to_contain_text("资金未执行")
        expect(
            page.locator('[data-cx-result="decider-close"] .cx-execution-badge')
        ).to_contain_text("未结案")
        expect(page.locator('[data-cx-final="bedrock"] .cx-outcome')).to_contain_text("业务已完成")
        expect(page.locator('[data-cx-final="bedrock"] [data-cx-funds]')).to_contain_text("已落实")
        page.locator(".cx-final-grid").screenshot(path="artifacts/crypto-outcome-divergence.png")
        with page.expect_download() as download:
            page.locator("[data-cx-export]").click()
        outcomes = json.loads(Path(download.value.path()).read_text())["businessOutcomes"]
        assert outcomes["decider"]["complete"] is False
        assert outcomes["decider"]["fundsComplete"] is False
        assert outcomes["bedrock"]["complete"] is True
        page.unroute("**/api/crypto/decision", conservative_replay)
        run(workflow=True)
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("已结案")
        expect(page.locator('[data-cx-final="bedrock"] .cx-outcome')).to_contain_text("已结案")
        expect(page.locator(".cx-ledger")).to_contain_text("129.00 USDC")
        for provider in ("decider", "bedrock"):
            for stage in ("intake", "verify", "approve", "execute", "close"):
                step = page.locator(f'[data-cx-result="{provider}-{stage}"]')
                expect(step).to_be_visible()
                expect(step.locator(".cx-execution-badge")).to_have_text(
                    {
                        "intake": "已受理（模拟）",
                        "verify": "已核验",
                        "approve": "检查通过",
                        "execute": "模拟资金动作已落实",
                        "close": "已回复 · 已结案",
                    }[stage]
                )
                expect(step.locator(".cx-step-timing")).to_contain_text("记录于")
                expect(step.locator(".cx-step-actual")).not_to_contain_text("尚未执行")
            expect(page.locator(f'[data-cx-result="{provider}-verify"]')).to_contain_text(
                "链上确认 12/12"
            )
            expect(page.locator(f'[data-cx-final="{provider}"] .cx-final-reply')).to_contain_text(
                "模拟订单已确认收款"
            )
        page.locator(".cx-execution-results").screenshot(
            path="artifacts/crypto-results-complete-desktop.png"
        )

        page.locator('[data-cx-case="refund"]').click()
        page.locator('[data-cx-event="approve"]').click()
        expect(page.locator("#toast")).to_contain_text("尚不满足")
        expect(page.locator(".cx-system-message.failed")).to_contain_text("交易证据未改变")

        # This deliberately wrong REPLAY recommendation tests the actual server's guard.
        # It is never labelled as a real model output or included in benchmark results.
        def wrong_replay(route):
            response = route.fetch()
            data = response.json()
            body = route.request.post_data_json
            if (
                body["mode"] == "replay"
                and body["provider"] == "decider"
                and body["stage"] == "execute"
            ):
                data.update(choice="refund_payment", label="提交模拟退款", matches_reference=False)
            if body["provider"] == "decider" and body["stage"] == "close":
                data.update(choice="resolve", label="回复并结案", matches_reference=False)
            route.fulfill(response=response, json=data)

        page.route("**/api/crypto/decision", wrong_replay)
        run(workflow=True)
        expect(page.locator('[data-cx-final="decider"]')).to_contain_text("已处理 5/5 步")
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("持续跟进")
        expect(page.locator('[data-cx-final="bedrock"] .cx-outcome')).to_contain_text("持续跟进")
        expect(page.locator('[data-cx-result="decider-execute"]')).to_contain_text(
            "保护调整 · 资金未执行 · 已挂起"
        )
        expect(page.locator('[data-cx-result="decider-execute"] .cx-step-choice')).to_contain_text(
            "提交模拟退款"
        )
        expect(page.locator('[data-cx-result="decider-execute"] .cx-step-output')).to_contain_text(
            "挂起并跟进"
        )
        expect(page.locator('[data-cx-result="decider-close"]')).to_contain_text("回复并持续跟进")
        expect(page.locator('[data-cx-final="decider"] .cx-blockers')).to_contain_text(
            "退款地址尚未验证"
        )
        expect(page.locator('[data-cx-final="decider"] .cx-blockers')).to_contain_text(
            "退款尚未获得人工审批"
        )
        expect(page.locator(".cx-audit-list")).to_contain_text("保护调整")
        assert page.locator(".cx-ledger").count() == 0
        page.locator(".cx-execution-results").screenshot(
            path="artifacts/crypto-flexible-held-desktop.png"
        )
        page.unroute("**/api/crypto/decision", wrong_replay)
        page.locator("[data-cx-reset]").click()

        # An execution request failure must remain visible in the step and final
        # result. Retrying resumes after completed steps, without losing the error.
        def failed_execution(route):
            if route.request.post_data_json["stage"] == "verify":
                route.fulfill(status=503, json={"detail": "测试执行服务暂不可用"})
            else:
                route.continue_()

        page.route("**/api/crypto/apply", failed_execution)
        run(workflow=True)
        for provider in ("decider", "bedrock"):
            expect(page.locator(f'[data-cx-final="{provider}"] .cx-outcome')).to_contain_text(
                "执行失败"
            )
            expect(page.locator(f'[data-cx-result="{provider}-verify"]')).to_contain_text(
                "测试执行服务暂不可用"
            )
            expect(page.locator(f'[data-cx-result="{provider}-approve"]')).to_contain_text(
                "前序中断 · 未执行"
            )
        page.unroute("**/api/crypto/apply", failed_execution)
        apply()
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("持续跟进")
        expect(page.locator('[data-cx-result="decider-verify"] .cx-step-attempt')).to_contain_text(
            "此前请求失败"
        )
        page.locator("[data-cx-reset]").click()

        # No output may be called executed when the model request failed.
        def failed_decision(route):
            if route.request.post_data_json["provider"] == "decider":
                route.fulfill(status=503, json={"detail": "测试模型暂不可用"})
            else:
                route.continue_()

        page.route("**/api/crypto/decision", failed_decision)
        page.locator("[data-cx-start]").click()
        expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=30000)
        expect(page.locator('[data-cx-final="decider"]')).to_contain_text("已处理 0/5 步")
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text(
            "模型调用失败"
        )
        expect(page.locator('[data-cx-result="decider-intake"]')).to_contain_text(
            "测试模型暂不可用"
        )
        expect(page.locator('[data-cx-final="bedrock"] .cx-outcome')).to_contain_text("持续跟进")
        page.unroute("**/api/crypto/decision", failed_decision)
        page.locator("[data-cx-reset]").click()

        for event in ["verify_address", "approve"]:
            page.locator(f'[data-cx-event="{event}"]').click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=10000)
            expect(page.locator(f'[data-cx-event-notice="{event}"]').last).to_contain_text(
                "模拟交易已推进"
            )
        run("live" if args.live else "replay", workflow=args.live)
        if args.live:
            expect(page.locator(".cx-summary-note")).to_contain_text("已对比 5/5")
            for provider in ("decider", "bedrock"):
                expect(page.locator(f".cx-lane.{provider} .cx-decision")).to_contain_text(
                    "真实模型建议"
                )
        page.locator('.cx-flow-track [data-cx-stage="execute"]').click()
        page.locator(".cx-comparison").screenshot(path="artifacts/crypto-comparison-desktop.png")
        apply()
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("已结案")
        expect(page.locator(".cx-ledger")).to_contain_text("250.00 USDC")
        expect(page.locator(".cx-bubble.agent").last).to_contain_text("没有广播链上交易")
        page.locator(".cx-workspace").screenshot(
            path="artifacts/crypto-refund-completed-desktop.png"
        )

        with page.expect_download() as download:
            page.locator("[data-cx-export]").click()
        data = json.loads(Path(download.value.path()).read_text())
        assert any(row.get("event") == "verify_address" for row in data["conversation"])
        assert any(row["kind"] == "reply" for row in data["conversation"])
        assert data["businessOutcomes"]["decider"]["fundsComplete"] is True
        assert data["businessOutcomes"]["decider"]["complete"] is True
        if args.live:
            for stage in ["intake", "verify", "approve", "execute", "close"]:
                a, b = (data["results"][provider][stage] for provider in ("decider", "bedrock"))
                assert a["source"] == b["source"] == "live"
                assert a["input_hash"] == b["input_hash"]
                assert a["timings"]["backend_total_ms"] > 0
                assert b["timings"]["backend_total_ms"] > 0
                assert b["model"] == "us.openai.gpt-6.1-sol"
                assert b["usage"]["input_tokens"] > 0
            assert data["results"]["decider"]["execute"]["probabilities"]
        args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

        for width in [390, 320]:
            page.set_viewport_size({"width": width, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            page.locator(".cx-order").screenshot(path=f"artifacts/crypto-order-{width}.png")
            page.locator(".cx-lane.bedrock").screenshot(
                path=f"artifacts/crypto-bedrock-{width}.png"
            )
            page.locator(".cx-final-grid").screenshot(
                path=f"artifacts/crypto-final-results-{width}.png"
            )
            page.locator(".cx-execution-step").nth(3).screenshot(
                path=f"artifacts/crypto-step-results-{width}.png"
            )
            page.locator(".cx-conversation").screenshot(
                path=f"artifacts/crypto-conversation-{width}.png"
            )
        for scenario, event, evidence, amount in [
            ("underpaid", "topup", "差额 0.20 USDT", "100.00 USDT"),
            ("settlement", "settle", "耗时 120 分钟 / SLA 60 分钟", "4,800.00 USDC"),
        ]:
            page.locator(f'[data-cx-case="{scenario}"]').click()
            run(workflow=True)
            for provider in ("decider", "bedrock"):
                expect(page.locator(f'[data-cx-result="{provider}-verify"]')).to_contain_text(
                    evidence
                )
                expect(page.locator(f'[data-cx-final="{provider}"] .cx-outcome')).to_contain_text(
                    "持续跟进"
                )
            page.locator(f'[data-cx-event="{event}"]').click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=10000)
            expect(page.locator(f'[data-cx-event-notice="{event}"]')).to_contain_text(
                "99.80 → 100.00 USDT" if event == "topup" else "未到账 → 已到账"
            )
            run(workflow=True)
            for provider in ("decider", "bedrock"):
                expect(page.locator(f'[data-cx-final="{provider}"] .cx-outcome')).to_contain_text(
                    "已结案"
                )
                expect(
                    page.locator(f'[data-cx-final="{provider}"] .cx-final-facts')
                ).to_contain_text(amount)
        # Per-case memory and edits must invalidate old results.
        page.locator('[data-cx-case="pending"]').click()
        expect(page.locator('[data-cx-final="decider"] .cx-outcome')).to_contain_text("已结案")
        page.locator("[data-cx-reset]").click()
        expect(page.locator(".cx-lane.decider .cx-model-count")).to_have_text("0/5")
        expect(page.locator(".cx-system-message")).to_have_count(0)
        expect(page.locator(".cx-bubble.agent")).to_have_count(0)
        page.locator(".cx-evidence summary").click()
        amount = page.locator('[data-cx-field="received"]')
        previous_amount = amount.input_value()
        amount.fill("")
        amount.press("Tab")
        expect(amount).to_have_value(previous_amount)
        expect(page.locator("#toast")).to_contain_text("业务证据未修改")
        page.locator('[data-cx-field="risk_flag"]').check()
        expect(page.locator(".cx-fact-chips")).to_contain_text("待人工风控")
        expect(page.locator(".cx-system-message")).to_contain_text("业务证据已更新")
        page.locator("#logout-button").click()
        expect(page.locator("#login-page")).to_be_visible()
        assert page.request.get(args.url + "/api/crypto/catalog").status == 401
        assert not errors, errors
        browser.close()
    print(
        "Payment UI passed: processed steps distinguished from business completion, provider divergence, blocked funds and reasons, original choices, failures/retry, ledger, outcome export, mobile, auth."
    )
    print("Live comparison:", args.live, "Results:", args.output)


if __name__ == "__main__":
    main()
