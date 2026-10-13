"""Build a pinned third-party ranking snapshot; never fetch rankings per request.

LiveBench/MTEB public results work without a key. Artificial Analysis uses its
official API only, with a server-side key file. Missing metrics stay missing.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MTEB_REVISION = "34a4409680a1deeb9ffc06942be546c6bed6a3e8"
LIVEBENCH_RELEASE = "2026_06_25"


def fetch(url, headers=None):
    with urlopen(Request(url, headers=headers or {}), timeout=45) as response:
        return response.read()


def number(value):
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("Invalid benchmark metric")
    return result


def livebench(mappings, evidence):
    base = "https://livebench.ai/"
    urls = {
        "scores": f"{base}table_{LIVEBENCH_RELEASE}.csv",
        "categories": f"{base}categories_{LIVEBENCH_RELEASE}.json",
        "costs": f"{base}cost_{LIVEBENCH_RELEASE}.csv",
    }
    raw = {key: fetch(url) for key, url in urls.items()}
    for key, value in raw.items():
        evidence.append({"url": urls[key], "sha256": hashlib.sha256(value).hexdigest()})
    scores = {r["model"]: r for r in csv.DictReader(io.StringIO(raw["scores"].decode()))}
    costs = {r["model"]: r for r in csv.DictReader(io.StringIO(raw["costs"].decode()))}
    categories = json.loads(raw["categories"])
    rows = {}
    for mid, source_id in mappings["livebench"].items():
        if source_id not in scores:
            continue
        row = scores[source_id]
        category_scores = {}
        for category, tasks in categories.items():
            values = [number(row.get(task)) for task in tasks]
            category_scores[category] = mean(values) if all(v is not None for v in values) else None
        if any(v is None for v in category_scores.values()):
            continue  # Do not rank a partial evaluation against complete evaluations.
        cost = costs.get(source_id, {})
        rows[mid] = {
            "source": "livebench",
            "source_id": source_id,
            "source_url": base,
            "benchmark_configuration": source_id,
            "request_fields": mappings["livebench_request_fields"].get(mid, {}),
            "configuration_note": "按映射请求推理配置；token 上限及运行环境与基准测试不完全相同。",
            "metrics": {
                "quality": mean(category_scores.values()),
                "coding": category_scores["Coding"],
                "reasoning": category_scores["Reasoning"],
                "language": category_scores["Language"],
                "input_price": number(cost.get("input_price_per_million")),
                "output_price": number(cost.get("output_price_per_million")),
                "output_tps": None,
                "ttft_seconds": None,
            },
            "category_scores": category_scores,
        }
    return rows, {
        "id": "livebench",
        "name": "LiveBench",
        "url": base,
        "release": LIVEBENCH_RELEASE.replace("_", "-"),
        "quality_label": "LiveBench 各类别均分",
        "coding_label": "LiveBench Coding",
        "speed_available": False,
        "note": "分数按官方类别分组计算；价格来自同批次 cost CSV，是外部参考价，非 Bedrock 报价。",
    }


def artificial_analysis(mappings, key_file, evidence):
    if not key_file:
        raise ValueError("--aa-key-file is required for the Artificial Analysis API")
    key = Path(key_file).expanduser().read_text().strip()
    if not key:
        raise ValueError("Empty Artificial Analysis key file")
    url = "https://artificialanalysis.ai/api/v2/data/llms/models"
    raw = fetch(url, {"x-api-key": key})
    evidence.append({"url": url, "sha256": hashlib.sha256(raw).hexdigest()})
    data = {m["slug"]: m for m in json.loads(raw)["data"]}
    rows = {}
    for mid, slug in mappings["artificial_analysis"].items():
        if slug not in data:
            continue
        row = data[slug]
        evaluation, price = row.get("evaluations", {}), row.get("pricing", {})
        rows[mid] = {
            "source": "artificial_analysis",
            "source_id": row["id"],
            "source_slug": slug,
            "source_url": f"https://artificialanalysis.ai/models/{slug}",
            "benchmark_configuration": row["name"],
            "request_fields": {"reasoning": {"effort": "low"}} if mid.startswith("openai.") else {},
            "configuration_note": "只映射明确型号与推理档位；基准端点和 Bedrock 性能可能不同。",
            "metrics": {
                "quality": number(evaluation.get("artificial_analysis_intelligence_index")),
                "coding": number(evaluation.get("artificial_analysis_coding_index")),
                "reasoning": number(evaluation.get("artificial_analysis_math_index")),
                "language": None,
                "input_price": number(price.get("price_1m_input_tokens")),
                "output_price": number(price.get("price_1m_output_tokens")),
                "output_tps": number(row.get("median_output_tokens_per_second")),
                "ttft_seconds": number(row.get("median_time_to_first_token_seconds")),
            },
        }
    return rows, {
        "id": "artificial_analysis",
        "name": "Artificial Analysis",
        "url": "https://artificialanalysis.ai/",
        "release": None,
        "quality_label": "Artificial Analysis Intelligence Index",
        "coding_label": "Artificial Analysis Coding Index",
        "speed_available": True,
        "note": "Data provided by Artificial Analysis. 速度/价格为第三方参考，非本项目 Bedrock 实测或报价。",
    }


def embeddings(mappings, evidence):
    rows = {}
    revisions = set()
    for mid, model in mappings["mteb"].items():
        url = (
            f"https://raw.githubusercontent.com/embeddings-benchmark/results/{MTEB_REVISION}"
            f"/results/{model}/1/MIRACLRetrievalHardNegatives.json"
        )
        raw = fetch(url)
        evidence.append({"url": url, "sha256": hashlib.sha256(raw).hexdigest()})
        data = json.loads(raw)
        revisions.add(data["dataset_revision"])
        subsets = {
            s["hf_subset"]: number(s["ndcg_at_10"])
            for s in data["scores"]["dev"]
            if s["hf_subset"] in {"en", "zh"}
        }
        if set(subsets) != {"en", "zh"}:
            raise ValueError("MTEB result missing matching English/Chinese subsets")
        rows[mid] = {
            "source": "mteb",
            "source_id": model,
            "source_url": url,
            "benchmark_configuration": "MIRACLRetrievalHardNegatives · dev · en/zh · float",
            "request_fields": {},
            "metrics": {"retrieval": mean(subsets.values()) * 100},
            "subsets": subsets,
            "dataset_revision": data["dataset_revision"],
            "mteb_version": data["mteb_version"],
        }
    if len(revisions) != 1:
        raise ValueError("MTEB datasets differ; refusing incomparable retrieval scores")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", choices=["livebench", "artificial-analysis"], default="livebench"
    )
    parser.add_argument("--aa-key-file")
    parser.add_argument("--output", type=Path, default=ROOT / "app/routing_rankings.json")
    args = parser.parse_args()
    mappings = json.loads((ROOT / "app/routing_mappings.json").read_text())
    evidence = []
    if args.source == "livebench":
        rows, profile = livebench(mappings, evidence)
    else:
        rows, profile = artificial_analysis(mappings, args.aa_key_file, evidence)
    if len(rows) < 3:
        raise ValueError("Too few mapped LLMs; existing snapshot not replaced")
    rows.update(embeddings(mappings, evidence))
    snapshot = {
        "schema_version": 1,
        "profile": profile,
        "embedding_source": {
            "name": "MTEB",
            "url": "https://huggingface.co/spaces/mteb/leaderboard",
            "revision": MTEB_REVISION,
            "metric": "MIRACL hard negatives dev · en/zh mean nDCG@10 × 100",
            "note": "本项目取中英文两个子集均分，不是 MTEB 总榜；CC0 结果，提交结果可来自模型提供方。",
        },
        "entries": rows,
        "evidence": evidence,
    }
    snapshot["version"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    snapshot["captured_at"] = datetime.now(UTC).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(args.output)
    print(
        f"Saved {len(rows)} exact mappings, source={profile['name']}, version={snapshot['version']}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # HTTP error messages do not include the secret request header.
        print(f"Ranking refresh failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        sys.exit(1)
