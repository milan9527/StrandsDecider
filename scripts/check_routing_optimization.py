"""Capture paired routing comparisons. Replay by default; --live makes real calls."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

PROVIDERS = ("decider", "jev", "bedrock")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8021")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--execute-targets", action="store_true")
    parser.add_argument(
        "--chromium",
        type=Path,
        default=Path("/home/ec2-user/.cache/ms-playwright/chromium-1243/chrome-linux-arm64/chrome"),
    )
    args = parser.parse_args()
    if args.execute_targets and not args.live:
        parser.error("--execute-targets requires --live")
    if args.output.exists() or args.rounds < 1:
        parser.error("Use a new output directory and a positive round count")
    args.output.mkdir(parents=True)
    credentials = json.loads(args.credentials.read_text())
    data = {
        "started_at": datetime.now(UTC).isoformat(),
        "url": args.url,
        "live": args.live,
        "warmups": [],
        "runs": [],
        "calls": [],
        "browser_errors": [],
        "gpu_mutations": [],
        "method": "Paired comparison sharing each workflow result. Original model choice and "
        "enhanced-evidence model choice use the same workflow, catalog and candidate IDs/order. Target calls "
        "are separate; no retry, configuration change or substitution.",
    }
    phase = "setup"

    def save():
        (args.output / "results.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=str(args.chromium))
        page = browser.new_page(viewport={"width": 1600, "height": 1150})
        page.on("pageerror", lambda e: data["browser_errors"].append(str(e)))

        def deny(route):
            data["gpu_mutations"].append(route.request.url)
            route.fulfill(status=409, json={"detail": "Audit prohibits GPU lifecycle changes"})

        def record(response):
            if response.url.endswith(
                ("/api/routing/decision", "/api/routing/rank", "/api/routing/execute")
            ):
                data["calls"].append(
                    {
                        "at": datetime.now(UTC).isoformat(),
                        "phase": phase,
                        "path": response.url.split("/api/")[-1],
                        "status": response.status,
                        "request": response.request.post_data_json,
                        "response": response.json(),
                    }
                )
                save()

        def export():
            with page.expect_download() as download:
                page.locator("[data-rt-export]").click()
            return json.loads(Path(download.value.path()).read_text())

        page.route("**/api/gpu/start", deny)
        page.route("**/api/gpu/stop", deny)
        page.on("response", record)
        page.goto(args.url + "/#routing", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".rt-case")).to_have_count(4, timeout=30000)
        expect(page.locator('[data-rt-field="priority"]')).to_have_count(0)
        catalog = page.request.get(args.url + "/api/routing/catalog").json()
        if args.live:
            phase = "warmup"
            for provider in PROVIDERS:
                flow = None
                for stage, variant in (
                    ("workflow", "original"),
                    ("model", "original"),
                    ("model", "optimized"),
                ):
                    payload = {
                        "task": {"text": catalog["cases"][0]["task"]},
                        "provider": provider,
                        "stage": stage,
                        "strategy": variant,
                        "mode": "live",
                        "catalog_version": catalog["version"],
                        "ranking_version": catalog["rankings"]["version"],
                    }
                    if flow:
                        payload["workflow"] = flow
                    if variant == "optimized":
                        payload["evidence_version"] = catalog["evidence_optimization"]["version"]
                    response = page.request.post(
                        args.url + "/api/routing/decision",
                        data=payload,
                        headers={"X-Decider-Client": "web"},
                        timeout=60000,
                    )
                    data["warmups"].append(
                        {"request": payload, "status": response.status, "response": response.json()}
                    )
                    save()
                    # Preserve failure; don't retry it or abort subsequent independent samples.
                    if not response.ok:
                        break
                    if stage == "workflow":
                        flow = response.json()["choice"]
                    print("Warmup", provider, stage, variant, flush=True)
        for round_index in range(args.rounds):
            phase = f"routing-{round_index + 1}"
            page.locator("[data-rt-strategy]").select_option("compare")
            page.locator("[data-rt-mode]").select_option("live" if args.live else "replay")
            page.locator("[data-rt-all]").click()
            expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=420000)
            result = export()
            for case, w in result["cases"].items():
                assert w["runStrategy"] == "compare"
                for p in PROVIDERS:
                    before, after = w["sides"][p], w["optimizedSides"][p]
                    if before["steps"] and after["steps"]:
                        assert before["steps"][0]["input_hash"] == after["steps"][0]["input_hash"]
                        assert before["steps"][0]["choice"] == after["steps"][0]["choice"]
                    for variant, side in (("original", before), ("optimized", after)):
                        if len(side["steps"]) == 2:
                            step = side["steps"][1]
                            assert step["source"] == ("live" if args.live else "rule_replay")
                            assert step["strategy"] == variant
                            assert step["model_input"] is not None
                    if len(before["steps"]) == len(after["steps"]) == 2:
                        orig, opt = before["steps"][1], after["steps"][1]
                        assert list(orig["model_input"]["questions"]["action"]["criteria"]) == list(
                            opt["model_input"]["questions"]["action"]["criteria"]
                        )
                        assert orig["input_hash"] != opt["input_hash"]
                    if not args.live:
                        assert not before["error"] and not after["error"]
                print(
                    "Round",
                    round_index + 1,
                    case,
                    {
                        p: {
                            "before": w["sides"][p]["steps"][-1].get("label"),
                            "after": w["optimizedSides"][p]["steps"][-1].get("label"),
                        }
                        for p in PROVIDERS
                        if w["sides"][p]["steps"]
                    },
                    flush=True,
                )
            data["runs"].append(result)
            save()
        for case in result["cases"]:
            page.locator(f'[data-rt-case="{case}"]').click()
            if args.execute_targets:
                phase = f"targets-{case}"
                page.locator("[data-rt-execute-all]").click()
                expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=420000)
                data["execution_export"] = export()
                save()
                print("Executed", case, flush=True)
            page.locator(".rt-comparison").screenshot(
                path=str(args.output / f"{case}-comparison.png")
            )
            page.locator("#rt-results").screenshot(path=str(args.output / f"{case}-results.png"))
        if not args.live:
            # A failed original selection must not erase the independent enhanced-evidence model branch.
            def fail_second_step(route):
                if (
                    route.request.post_data_json["stage"] == "model"
                    and route.request.post_data_json.get("strategy") == "original"
                ):
                    route.fulfill(
                        status=503, json={"detail": "Injected original-selection failure"}
                    )
                else:
                    route.continue_()

            page.route("**/api/routing/decision", fail_second_step)
            page.locator("[data-rt-start]").click()
            expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=30000)
            failed = export()["cases"]["retrieval"]
            assert all(failed["sides"][p]["error"] for p in PROVIDERS)
            assert all(
                failed["optimizedSides"][p]["steps"][-1]["selected_model"] for p in PROVIDERS
            )
            page.unroute("**/api/routing/decision", fail_second_step)
            # Both standalone profiles retain two model decisions.
            for profile in ("optimized", "original"):
                page.locator("[data-rt-strategy]").select_option(profile)
                page.locator("[data-rt-start]").click()
                expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=30000)
                expect(page.locator(".rt-side")).to_have_count(3)
                w = export()["cases"]["retrieval"]
                active = w["optimizedSides"] if profile == "optimized" else w["sides"]
                inactive = w["sides"] if profile == "optimized" else w["optimizedSides"]
                assert all(
                    len(active[p]["steps"]) == 2 and not inactive[p]["steps"] for p in PROVIDERS
                )
            page.locator("#rt-task").fill("生成新任务的索引向量")
            page.locator("#rt-task").blur()
            expect(page.locator("[data-rt-execute-all]")).to_have_count(0)
            assert all(not s["steps"] for s in export()["cases"]["retrieval"]["sides"].values())
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert not data["browser_errors"], data["browser_errors"]
        assert not data["gpu_mutations"], data["gpu_mutations"]
        assert not any(c["path"] == "routing/rank" for c in data["calls"])
        data.update(finished_at=datetime.now(UTC).isoformat(), mobile_overflow=False)
        save()
        browser.close()
    print(json.dumps({"passed": True, "live": args.live, "output": str(args.output)}))


if __name__ == "__main__":
    main()
