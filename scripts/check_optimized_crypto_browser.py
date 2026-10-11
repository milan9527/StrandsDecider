"""Compare baseline/optimized payment inputs and execution in all four scenarios."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".deployment/optimized-browser.json"))
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Path("artifacts").mkdir(exist_ok=True)
    errors, observations = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/#crypto", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".cx-case")).to_have_count(4)
        expect(page.locator("[data-cx-test-kind] option")).to_have_text(
            ["固定流程", "优化流程", "自主闭环"]
        )
        page.locator(f'[data-cx-mode="{"live" if args.live else "replay"}"]').click()

        def export():
            with page.expect_download() as download:
                page.locator("[data-cx-export]").click()
            return json.loads(Path(download.value.path()).read_text())

        for case in ("pending", "underpaid", "refund", "settlement"):
            page.locator(f'[data-cx-case="{case}"]').click()
            observations[case] = {}
            for kind, profile in (("workflow", "baseline"), ("optimized", "optimized")):
                page.locator("[data-cx-test-kind]").select_option(kind)
                if profile == "optimized":
                    expect(page.locator(".cx-profile-note")).to_be_visible()
                page.locator("[data-cx-start]").click()
                expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=180000)
                expect(page.locator(".cx-turn-pending")).to_have_count(0)
                expected_kind = "fixed" if profile == "baseline" else "optimized"
                expected_label = "固定流程" if profile == "baseline" else "优化流程"
                expect(page.locator(".cx-summary-note")).to_contain_text(expected_label)
                result = export()
                observations[case][profile] = result
                args.output.write_text(json.dumps(observations, ensure_ascii=False, indent=2))
                assert result["workflowKind"] == expected_kind
                latest = [r for r in result["dialogues"] if r["run"] == result["dialogueRun"]]
                assert len(latest) == 5
                for row in latest:
                    assert row["kind"] == expected_kind
                    a, b = row["sides"]["decider"], row["sides"]["bedrock"]
                    assert a["request"]["snapshot"] == b["request"]["snapshot"]
                    for side in (a, b):
                        assert side["request"]["input_profile"] == profile
                        assert not side["pending"]
                        if side.get("error"):
                            assert args.live, side["error"]
                            continue
                        data = side["result"]
                        assert data["input_profile"] == profile
                        assert data["source"] == ("live" if args.live else "rule_replay")
                        fields = json.loads(data["model_input"]["state"])
                        if profile == "optimized":
                            assert ("refund_approved" in fields) == (case == "refund")
                            assert ("settled" in fields) == (case == "settlement")
                            assert ("confirmed" in fields) == (case != "settlement")
                        if not args.live:
                            assert data["timings"] is None
                            assert len(side["executions"]) == 1
                    if a.get("result") and b.get("result"):
                        assert a["result"]["model_input"] == b["result"]["model_input"]
                        assert a["result"]["input_hash"] == b["result"]["input_hash"]
                if profile == "optimized":
                    expect(page.locator("[data-cx-input-profile]")).to_have_count(5)
                    for provider in ("decider", "bedrock"):
                        if all(r["sides"][provider].get("result") for r in latest):
                            expect(page.locator(f'[data-cx-final="{provider}"]')).to_contain_text(
                                "已处理 5/5 步"
                            )
                    baseline = observations[case]["baseline"]
                    assert baseline["snapshot"] == result["snapshot"]
                    # Changing test selection does not relabel the already completed results.
                    page.locator("[data-cx-test-kind]").select_option("workflow")
                    expect(page.locator(".cx-summary-note")).to_contain_text("优化流程")
                    page.locator("[data-cx-dialogue-run]").select_option("1")
                    expect(page.locator(".cx-turn").first).to_contain_text("固定流程")
                    expect(page.locator("[data-cx-input-profile]")).to_have_count(0)
                    page.locator("[data-cx-dialogue-run]").select_option("2")
                    expect(page.locator(".cx-turn").first).to_contain_text("优化流程")
                    page.locator("[data-cx-test-kind]").select_option("optimized")
            page.screenshot(
                path=f"artifacts/optimized-{case}-{'live' if args.live else 'replay'}.png"
            )

        if not args.live:
            # Single-step diagnostics must clear the previous profile's results.
            page.locator("[data-cx-test-kind]").select_option("workflow")
            page.locator('[data-cx-panel="diagnostics"] > summary').click()
            page.locator('[data-cx-run="step"]').click()
            expect(page.locator("[data-cx-start]")).to_be_enabled(timeout=30000)
            expect(page.locator(".cx-lane.decider .cx-model-count")).to_have_text("1/5")
            expect(page.locator(".cx-summary-note")).to_contain_text("固定流程")
            page.locator('[data-cx-panel="diagnostics"] > summary').click()
        for width in (390, 320):
            page.set_viewport_size({"width": width, "height": 844})
            page.locator("[data-cx-test-kind]").select_option("optimized")
            page.evaluate("window.scrollTo(0, 0)")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (
                width
            )
            page.screenshot(path=f"artifacts/optimized-mobile-{width}.png")
        browser.close()
    assert not errors, errors
    print(
        "Verified: four scenarios, baseline/optimized profiles, identical provider payloads, "
        "execution records, history labels, exports and mobile layout. "
        + ("Real model observations saved." if args.live else "Replay only; no real model calls.")
    )


if __name__ == "__main__":
    main()
