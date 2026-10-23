"""Package the frozen vision experiment for the authenticated demo API."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    source = ROOT / "validation/vision"
    manifest = json.loads((source / "cases.json").read_text())
    receipts = [json.loads(line) for line in (source / "results/receipts.jsonl").read_text().splitlines()]
    labels = [
        "支付成功 · 英文", "等待链上确认", "付款失败", "支付成功 · 中文",
        "重复付款退款", "支付报错", "账号锁定", "币种咨询",
        "完整凭证", "缺少签名", "缺少交易编号", "编号和签名都缺失",
    ]
    stages = {"image": "original", "reverse": "reverse", "no_image": "no_image", "blank": "blank"}
    output = ROOT / "app/vision_assets"
    output.mkdir(exist_ok=True)
    assets = ROOT / "frontend/static/vision"
    assets.mkdir(exist_ok=True)
    cases = []
    for case, title in zip(manifest["cases"], labels, strict=True):
        image = source / case["image"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == case["sha256"]
        shutil.copy2(image, output / image.name)
        shutil.copy2(image, assets / image.name)
        recordings = {}
        for row in receipts:
            if row["case"] == case["id"] and row["stage"] in stages and row["repetition"] == 0:
                assert row["http_status"] == 200
                recordings[stages[row["stage"]]] = {
                    "captured_at": row["started_at"], "response": row["response"],
                }
        cases.append({**case, "title": title, "image": image.name, "recordings": recordings})
    shutil.copy2(source / "images/blank.png", output / "blank.png")
    shutil.copy2(source / "images/blank.png", assets / "blank.png")
    (output / "catalog.json").write_text(json.dumps({
        "captured_at": "2026-10-23", "cases_sha256": hashlib.sha256((source / "cases.json").read_bytes()).hexdigest(),
        "cases": cases,
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"Packaged {len(cases)} cases with four actual recorded conditions each")


if __name__ == "__main__":
    main()
