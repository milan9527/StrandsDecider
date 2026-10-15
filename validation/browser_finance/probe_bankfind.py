import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": 1440, "height": 1000})
        await page.goto(
            "https://banks.data.fdic.gov/bankfind-suite/bankfind",
            wait_until="domcontentloaded",
            timeout=35000,
        )
        await page.locator("#text-filter-name").wait_for(timeout=15000)
        print(
            "select", await page.locator("#select-filter-name-cert-url").input_value(), flush=True
        )
        await page.locator("#text-filter-name").fill("JPMorgan Chase Bank")
        await page.locator("#findBankSearch").click()
        await page.wait_for_timeout(3500)
        d = await page.evaluate(
            """()=>({url:location.href,text:document.body.innerText,headings:[...document.querySelectorAll('h1,h2,h3')].map(e=>e.innerText), links:[...document.querySelectorAll('a[href]')].filter(e=>e.innerText.includes('JPMorgan')).map(e=>({text:e.innerText,href:e.href})),main:[...document.querySelectorAll('main,[role=main]')].map(e=>({tag:e.tagName,id:e.id}))})"""
        )
        (Path(__file__).resolve().parent / "preflight/bankfind-operated.json").write_text(
            json.dumps(d, indent=2)
        )
        print(json.dumps(d, ensure_ascii=False)[:5500])
        await b.close()


asyncio.run(main())
