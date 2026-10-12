"""Verify unified Decider / Jev / GPT workflows, metrics, failures and mobile layout."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

PROVIDERS = ["decider", "jev", "bedrock"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".deployment/triple-browser.json"))
    parser.add_argument("--live", action="store_true", help="Four optimized cases, 60 real calls")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Path("artifacts").mkdir(exist_ok=True)
    credentials = json.loads(args.credentials.read_text())
    records, errors, gpu_writes = {}, [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def prohibit_gpu(route):
            gpu_writes.append(route.request.url)
            route.fulfill(status=409, json={"detail": "Browser check never starts or stops GPU"})

        page.route("**/api/gpu/start", prohibit_gpu)
        page.route("**/api/gpu/stop", prohibit_gpu)
        page.goto(args.url + "/#crypto", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".cx-case")).to_have_count(4)
        expect(page.locator("[data-cx-model-pair]")).to_have_count(0)
        expect(page.locator(".cx-comparison-title h1")).to_have_text(
            "Strands Decider vs Jev vs GPT"
        )
        page.locator(f'[data-cx-mode="{"live" if args.live else "replay"}"]').click()

        def export():
            with page.expect_download() as download:
                page.locator("[data-cx-export]").click()
            return json.loads(Path(download.value.path()).read_text())

        def run(method):
            page.locator("[data-cx-test-kind]").select_option(method)
            page.locator("[data-cx-start]").click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=240000)
            expect(page.locator(".cx-turn-pending")).to_have_count(0)
            return export()

        for case in ("pending", "underpaid", "refund", "settlement"):
            page.locator(f'[data-cx-case="{case}"]').click()
            records[case] = {}
            for method in ("optimized",) if args.live else ("workflow", "optimized", "loop"):
                result = run(method)
                records[case][method] = result
                args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
                assert result["comparisonProviders"] == PROVIDERS
                latest = [r for r in result["dialogues"] if r["run"] == result["dialogueRun"]]
                assert latest
                for row in latest:
                    assert row["providers"] == PROVIDERS
                    for side in row["sides"].values():
                        assert not side["pending"] and not side.get("error"), side.get("error")
                        if side.get("result"):
                            assert side["result"]["source"] == (
                                "live" if args.live else "rule_replay"
                            )
                for provider in PROVIDERS:
                    expect(page.locator(f'[data-cx-final="{provider}"]')).to_be_visible()
                    assert result["executions"][provider]
                    if method == "loop":
                        assert result["businessOutcomes"][provider]["complete"]
                    else:
                        assert len(result["executions"][provider]["audit"]) == 5
                if method != "loop":
                    assert len(latest) == 5
                    for row in latest:
                        outputs = [row["sides"][p]["result"] for p in PROVIDERS]
                        assert len({r["input_hash"] for r in outputs}) == 1
                        assert all(r["model_input"] == outputs[0]["model_input"] for r in outputs)
                    expect(page.locator(".cx-turn > .cx-turn-input")).to_have_count(5)
                    for provider in PROVIDERS:
                        expect(
                            page.locator(f'[data-cx-dialogue-output="{provider}"]')
                        ).to_have_count(5)
                if args.live:
                    assert all(
                        row["sides"]["jev"]["result"]["model"].startswith("jev-") for row in latest
                    )
                    page.locator(".cx-dialogue-feed").evaluate("(el) => el.scrollTop = 0")
                    page.screenshot(path=f"artifacts/triple-{case}-live.png", full_page=False)
            if not args.live:
                previous = records[case]["workflow"]
                page.locator("[data-cx-dialogue-run]").select_option(str(previous["dialogueRun"]))
                for provider in PROVIDERS:
                    expect(page.locator(f'[data-cx-dialogue-output="{provider}"]')).to_have_count(5)
                page.locator("[data-cx-dialogue-run]").select_option(str(result["dialogueRun"]))

        if not args.live:
            # Synthetic timings are only a UI regression fixture, never model measurements.
            def synthetic(route):
                body = route.request.post_data_json
                provider, stage = body["provider"], body["stage"]
                if provider == "jev" and stage == "approve":
                    route.fulfill(status=503, json={"detail": "Explicit test: Jev unavailable"})
                    return
                response = route.fetch(post_data=json.dumps({**body, "mode": "replay"}))
                data = response.json()
                data.update(source="live", model="synthetic-ui-fixture")
                data["timings"] = {
                    "backend_total_ms": {"decider": 10, "jev": 20, "bedrock": 30}[provider]
                }
                if provider == "bedrock" and stage == "intake":
                    data.update(
                        choice="refund_support",
                        label="Explicit test difference",
                        matches_reference=False,
                    )
                route.fulfill(json=data)

            page.route("**/api/crypto/decision", synthetic)
            page.locator('[data-cx-case="pending"]').click()
            page.locator('[data-cx-mode="live"]').click()
            result = run("workflow")
            assert "jev" not in result["executions"]
            for provider in ("decider", "bedrock"):
                assert len(result["executions"][provider]["audit"]) == 5
            for provider, total in (
                ("decider", "50.0 ms"),
                ("jev", "80.0 ms"),
                ("bedrock", "150.0 ms"),
            ):
                expect(page.locator(f".cx-speed-card.{provider} strong")).to_have_text(total)
            expect(page.locator(".cx-speed-card.jev .cx-relative-time")).to_have_text(
                "同输入 4 步 · 耗时为 Decider 的 2.0×"
            )
            expect(page.locator(".cx-speed-card.bedrock .cx-relative-time")).to_have_text(
                "同输入 5 步 · 耗时为 Decider 的 3.0×"
            )
            expect(page.locator(".cx-summary-note")).to_contain_text(
                "三模型同输入对比 4/5 步 · 存在选择差异 1 步"
            )
            expect(page.locator(".cx-compare-table tbody tr").nth(0)).to_contain_text("存在差异")
            expect(page.locator(".cx-compare-table tbody tr").nth(2)).to_contain_text("有调用失败")
            records["synthetic_ui_fixture_not_measurements"] = result
            page.unroute("**/api/crypto/decision", synthetic)

        for width in (390, 320, 768, 1440):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
            expect(page.locator("[data-cx-start]")).to_be_visible()
            expect(page.locator(".cx-speed-card")).to_have_count(3)
            if args.live and width == 390:
                page.screenshot(path="artifacts/triple-mobile-live.png", full_page=True)
        assert not errors, errors
        assert not gpu_writes, gpu_writes
        records["verification"] = {
            "mode": "live" if args.live else "replay_and_synthetic_ui_fixture",
            "page_errors": errors,
            "gpu_writes": gpu_writes,
        }
        args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        browser.close()
    print(
        f"PASS: three models, four cases, metrics, history, outputs and mobile layout; {args.output}"
    )


if __name__ == "__main__":
    main()
