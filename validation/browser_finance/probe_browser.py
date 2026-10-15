"""Read-only preflight of public websites; no model inference."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

URLS = {
    "wikipedia": "https://en.wikipedia.org/wiki/Main_Page",
    "cfpb": "https://www.consumerfinance.gov/consumer-tools/credit-cards/",
    "ecb": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
    "microsoft": "https://www.microsoft.com/investor/reports/ar25/index.html",
    "fdic": "https://www.fdic.gov/resources/deposit-insurance/understanding-deposit-insurance",
    "fred": "https://fred.stlouisfed.org/series/FEDFUNDS",
}


async def main():
    folder = Path(__file__).resolve().parent / "preflight"
    folder.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        async def inspect(name, url):
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1000}, locale="en-US"
            )
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(1500)
                data = await page.evaluate(
                    """() => ({title:document.title,url:location.href,text:document.body.innerText, headings:[...document.querySelectorAll('h1,h2,h3')].map(e=>e.innerText).filter(Boolean), controls:[...document.querySelectorAll('main a[href],#content a[href],article a[href],input:not([type=hidden]),button')].filter(e=>e.getBoundingClientRect().width>0 && e.getBoundingClientRect().height>0).map(e=>({tag:e.tagName,text:(e.innerText||e.getAttribute('aria-label')||e.placeholder||'').trim().slice(0,130),href:e.href||'',type:e.type||'',name:e.name||''})).filter(e=>e.text||e.tag==='INPUT')})"""
                )
                data["status"] = response.status if response else None
                (folder / f"{name}.json").write_text(json.dumps(data, indent=2))
                await page.screenshot(path=str(folder / f"{name}.png"), full_page=False)
                print(
                    json.dumps(
                        {
                            "site": name,
                            "status": data["status"],
                            "url": data["url"],
                            "title": data["title"],
                            "headings": data["headings"][:12],
                            "controls": data["controls"][:25],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            except Exception as exc:
                print(name, type(exc).__name__, str(exc)[:140], flush=True)
            finally:
                await context.close()

        await asyncio.gather(*(inspect(n, u) for n, u in URLS.items()))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
