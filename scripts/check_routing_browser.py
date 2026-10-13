"""Exercise the routing UI; replay by default, explicit --live for real comparisons."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8021")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--execute-targets",
        action="store_true",
        help="After live routing, execute one selected target per scenario",
    )
    args = parser.parse_args()
    if args.execute_targets and not args.live:
        parser.error("--execute-targets requires --live")
    if args.output.exists():
        parser.error("Use a new output directory to preserve previous evidence")
    args.output.mkdir(parents=True)
    credentials = json.loads(args.credentials.read_text())
    errors, forbidden = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def prohibit(route):
            forbidden.append(route.request.url)
            route.fulfill(
                status=409, json={"detail": "Browser audit prohibits GPU lifecycle changes"}
            )

        page.route("**/api/gpu/start", prohibit)
        page.route("**/api/gpu/stop", prohibit)
        page.goto(args.url + "/#routing", wait_until="domcontentloaded")
        page.locator("#login-username").fill(credentials["username"])
        page.locator("#login-password").fill(credentials["password"])
        page.locator("#login-submit").click()
        expect(page.locator(".rt-case")).to_have_count(4)
        expect(page.locator('[data-rt-field="capability"]')).to_have_count(0)
        expect(page.locator('[data-rt-field="priority"]')).to_have_count(0)
        if args.live:
            catalog = page.request.get(args.url + "/api/routing/catalog").json()
            case = catalog["cases"][0]
            warmups = {}
            for provider in ("decider", "jev", "bedrock"):
                flow = None
                for stage in ("workflow", "model"):
                    payload = {
                        "task": {"text": case["task"]},
                        "provider": provider,
                        "stage": stage,
                        "mode": "live",
                        "catalog_version": catalog["version"],
                        "ranking_version": catalog["rankings"]["version"],
                    }
                    if flow:
                        payload["workflow"] = flow
                    response = page.request.post(
                        args.url + "/api/routing/decision",
                        headers={"X-Decider-Client": "web"},
                        data=payload,
                        timeout=60000,
                    )
                    warmups[f"{provider}/{stage}"] = {
                        "status": response.status,
                        "result": response.json(),
                    }
                    (args.output / "warmups.json").write_text(
                        json.dumps(warmups, ensure_ascii=False, indent=2)
                    )
                    assert response.ok, (provider, stage, response.status, response.json())
                    flow = response.json()["choice"]
        page.locator("[data-rt-mode]").select_option("live" if args.live else "replay")
        page.locator("[data-rt-all]").click()
        expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=300000)
        with page.expect_download() as download:
            page.locator("[data-rt-export]").click()
        result = json.loads(Path(download.value.path()).read_text())
        (args.output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        for case, workspace in result["cases"].items():
            model_inputs = {}
            fingerprints = set()
            for provider, side in workspace["sides"].items():
                assert not side["error"], (case, provider, side["error"])
                assert len(side["steps"]) == 2, (case, provider)
                assert side["steps"][-1]["selected_model"]
                assert side["execution"] is None
                step = side["steps"][0]
                fingerprints.add(step["input_hash"])
                model_step = side["steps"][1]
                assert model_step["stage"] == "model"
                assert model_step["workflow"]["id"] == step["choice"]
                assert (
                    model_inputs.setdefault(step["choice"], model_step["input_hash"])
                    == model_step["input_hash"]
                )
                chosen = next(
                    row
                    for row in model_step["selection"]["candidates"]
                    if row["candidate_id"] == model_step["choice"]
                )
                assert chosen["model"]["id"] == model_step["selected_model"]["id"]
                for step in side["steps"]:
                    assert step["source"] in (
                        {"live", "single_candidate"}
                        if args.live
                        else {"rule_replay", "single_candidate"}
                    )
                    if not args.live:
                        assert step["timings"] is None and step["usage"] is None
            assert len(fingerprints) == 1, (case, "Classifier inputs differ")
            page.locator(f'[data-rt-case="{case}"]').click()
            expect(page.locator(".rt-round")).to_have_count(2)
            expect(page.locator(".rt-turn-output")).to_have_count(6)
            page.screenshot(path=str(args.output / f"{case}-desktop.png"), full_page=True)
        executions = {}
        if args.execute_targets:
            for case, workspace in result["cases"].items():
                page.locator(f'[data-rt-case="{case}"]').click()
                with page.expect_response(
                    lambda r: r.url.endswith("/api/routing/execute"), timeout=65000
                ) as response:
                    page.locator('[data-rt-execute="decider"]').click()
                reply = response.value
                executions[case] = {
                    "selected_by": "decider",
                    "workflow": workspace["sides"]["decider"]["steps"][0]["choice"],
                    "status": reply.status,
                    "result": reply.json(),
                }
                (args.output / "target-execution.json").write_text(
                    json.dumps(executions, ensure_ascii=False, indent=2)
                )
                expect(page.locator("[data-rt-start]")).to_be_enabled(timeout=65000)
                page.screenshot(path=str(args.output / f"{case}-execution.png"), full_page=True)
        # The whole catalog remains discoverable, including filtered-out capacity variants.
        page.locator("#rt-catalog > summary").click()
        model_count = len(page.request.get(args.url + "/api/routing/catalog").json()["models"])
        expect(page.locator("#rt-catalog-table table tbody tr")).to_have_count(model_count)
        page.locator("[data-rt-search]").fill("gpt-6-sol")
        expect(page.locator("#rt-catalog-table table tbody tr")).to_have_count(1)
        page.locator("[data-rt-search]").fill("")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors, errors
        assert not forbidden, forbidden
        (args.output / "verification.json").write_text(
            json.dumps(
                {
                    "live": args.live,
                    "cases": 4,
                    "route_steps": 24,
                    "executed_targets": args.execute_targets,
                    "target_results": {
                        case: {
                            "http_status": row["status"],
                            "complete": row["result"].get("complete", False),
                        }
                        for case, row in executions.items()
                    },
                    "browser_errors": errors,
                    "gpu_mutations": forbidden,
                    "mobile_overflow": False,
                },
                indent=2,
            )
        )
        browser.close()
    print(json.dumps({"passed": True, "live": args.live, "cases": 4, "output": str(args.output)}))


if __name__ == "__main__":
    main()
