import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    out = Path(__file__).resolve().parent / "preflight"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.goto(
            "https://fred.stlouisfed.org/series/FEDFUNDS", wait_until="domcontentloaded"
        )
        await page.wait_for_timeout(1500)
        print(
            "fred-inputs",
            await page.locator("input").evaluate_all(
                '(es)=>es.filter(e=>e.getBoundingClientRect().width).map(e=>({id:e.id,label:e.getAttribute("aria-label"),value:e.value,type:e.type}))'
            ),
            flush=True,
        )
        for label, value in [
            ("Change start date", "2024-01-01"),
            ("Change end date", "2024-12-31"),
        ]:
            field = page.get_by_label(label, exact=True)
            await field.fill(value)
            await field.press("Enter")
            await page.wait_for_timeout(1300)
        print(
            "fred-date-result",
            page.url,
            await page.locator("#input-cosd").input_value(),
            await page.locator("#input-coed").input_value(),
            flush=True,
        )
        await page.wait_for_timeout(1000)
        text = await page.locator("body").inner_text()
        (out / "fred-operated.json").write_text(
            json.dumps(
                {
                    "url": page.url,
                    "text": text,
                    "inputs": await page.locator("input").evaluate_all(
                        '(es)=>es.filter(e=>e.getBoundingClientRect().width).map(e=>({id:e.id,label:e.getAttribute("aria-label"),value:e.value,type:e.type}))'
                    ),
                },
                indent=2,
            )
        )
        print("fred-after", page.url, text[:2000], flush=True)
        for name, url in [
            (
                "ecb-usd",
                "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html",
            ),
            (
                "cfpb-dispute",
                "https://www.consumerfinance.gov/ask-cfpb/how-do-i-dispute-a-charge-on-my-credit-card-bill-en-61/",
            ),
            ("fdic-faq", "https://www.fdic.gov/resources/deposit-insurance/faq/"),
        ]:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(800)
            text = await page.locator("body").inner_text()
            headings = await page.locator("h1,h2,h3").all_inner_texts()
            (out / f"{name}.json").write_text(
                json.dumps({"url": page.url, "text": text, "headings": headings}, indent=2)
            )
            print(name, headings[:15], text[:500], flush=True)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
