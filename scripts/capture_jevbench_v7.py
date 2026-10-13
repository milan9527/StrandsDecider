"""Archive the public JevBench API board and take an unmodified browser screenshot."""

import hashlib
import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/presentations/v7"
URL = "https://benchmarkheaven.com/jev-models/api"


def main():
    sources = OUT / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    html = urllib.request.urlopen(URL, timeout=30).read()
    soup = BeautifulSoup(html, "html.parser")
    chunks = []
    for tag in soup.find_all("script"):
        match = re.fullmatch(r"self\.__next_f\.push\((.*)\)", (tag.string or "").strip())
        if match:
            data = json.loads(match.group(1))
            if len(data) > 1 and isinstance(data[1], str):
                chunks.append(data[1])
    stream = "".join(chunks)
    score_rows, info_rows = None, None
    for match in re.finditer(r'"rows":\[', stream):
        try:
            rows = json.JSONDecoder().raw_decode(stream[match.end() - 1 :])[0]
        except ValueError:
            continue
        if rows and isinstance(rows[0], dict):
            if "jevbench_score" in rows[0]:
                score_rows = rows
            elif "modelClass" in rows[0]:
                info_rows = rows
    assert score_rows and info_rows
    info = {row["key"]: row for row in info_rows}
    for row in score_rows:
        row["offering_metadata"] = info[row["key"]]
        row["capability_derived"] = (row["axes"]["intelligence"] + row["axes"]["calibration"]) / 2
    method = soup.find(id="jev16-method").get_text("\n", strip=True)
    (sources / "jevbench-method.txt").write_text(method + "\n")
    snapshot = {
        "captured_at": datetime.now(UTC).isoformat(),
        "url": URL,
        "board_version": "v1.7.46",
        "html_sha256": hashlib.sha256(html).hexdigest(),
        "ranked_rows": len(score_rows),
        "rows": score_rows,
        "interpretation": [
            "Public third-party observations, not new measurements by this project.",
            "API offerings include hosted open-weight models; this is not the self-hosted board.",
            "Intelligence and Calibration are normalized scores, not raw accuracy percentages.",
            "Composite is the equal-weight harmonic mean with low-axis gates.",
            "Cost is modeled list-price cost or an explicitly marked estimate, not an invoice.",
            "The board combines full-set and equated API subsets, with historical measurement dates.",
            "GPT-6.1 Sol and Strands Decider v19 are not ranked entries on this API board.",
        ],
    }
    (sources / "jevbench-api-20261012.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    )
    for name, url in [
        ("strands-introduction", "https://strandsagents.com/blog/introducing-strands-decider/"),
        (
            "decider-model-card",
            "https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v19/raw/main/README.md",
        ),
        ("jev-introduction", "https://typesafe.ai/blog/introducing-system-one-models-and-jev"),
    ]:
        content = urllib.request.urlopen(url, timeout=30).read()
        text = (
            content.decode()
            if name == "decider-model-card"
            else BeautifulSoup(content, "html.parser").get_text("\n", strip=True)
        )
        (sources / f"{name}.txt").write_text(text)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1.5)
        page.goto(URL, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        heading = page.get_by_role("heading").filter(has_text="Composite Score").first
        if heading.count():
            heading.scroll_into_view_if_needed()
            page.evaluate("window.scrollBy(0, -80)")
        path = OUT / "screenshots/jevbench-public-board.png"
        page.screenshot(path=str(path))
        (sources / "jevbench-screenshot.json").write_text(
            json.dumps(
                {
                    "url": URL,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "file": str(path.relative_to(OUT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "data_replaced": False,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        dismiss = page.get_by_role("button", name="Don't show again")
        if dismiss.count():
            dismiss.click()
        page.get_by_text("Jev 1.13.0", exact=True).first.scroll_into_view_if_needed()
        page.evaluate("window.scrollBy(0, 250)")
        path = OUT / "screenshots/jevbench-leaderboard.png"
        page.screenshot(path=str(path))
        (sources / "jevbench-leaderboard-screenshot.json").write_text(
            json.dumps(
                {
                    "url": URL,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "file": str(path.relative_to(OUT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "data_replaced": False,
                    "interaction": "Dismissed site banner and scrolled to ranked entries.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        browser.close()
    print(f"Archived {len(score_rows)} public API results and original board screenshot.")


if __name__ == "__main__":
    main()
