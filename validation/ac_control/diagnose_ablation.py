"""Explain gate errors and write exact per-case response examples after scoring."""

import argparse
import json
from pathlib import Path

from analyze import display_commands
from compare_resident import LABELS, MODEL_IDS
from prepare import save


def diagnose(run):
    rows = json.loads((run / "ablation_results.json").read_text())
    summary = json.loads((run / "ablation_summary.json").read_text())
    if summary["partial"]:
        raise ValueError("Final diagnostics require a complete run")
    diagnostics = {}
    text = [
        "# 两阶段错误定位与完整回答示例", "",
        "第一步选择需要下发的 Key，第二步才选取具体值。"
        "第一步漏选的 Key 无法由第二步补回；第一步多选的 Key 仍可以在第二步选 omit。", "",
        "以下门控指标只统计原规范20题、原始候选顺序。召回率分母为标准答案所需的40个 Key。", "",
        "| 模型 | 门控选中Key数 | 其中应当选中 | 所需Key召回 | 全部omit的用例 | 门控Key集合完全正确 | 最终指令完全正确 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider in MODEL_IDS:
        group = [r for r in rows if r["provider"] == provider and r["arm"] == "two_stage"
                 and r["dataset"] == "spec" and r["variant"] == "original"]
        selected_count = expected_count = true_positive = empty = key_exact = 0
        false_positive_keys, false_negative_keys = [], []
        for row in group:
            selected = set(row["gate_selected_keys"] or [])
            expected = {c["cmdKey"] for c in row["expected"]}
            selected_count += len(selected)
            expected_count += len(expected)
            true_positive += len(selected & expected)
            empty += not selected
            key_exact += selected == expected
            false_positive_keys += [{"case_id": row["case_id"], "key": key}
                                    for key in sorted(selected - expected)]
            false_negative_keys += [{"case_id": row["case_id"], "key": key}
                                    for key in sorted(expected - selected)]
        diagnostics[provider] = {
            "selected_keys": selected_count, "expected_keys": expected_count,
            "true_positive_keys": true_positive, "all_omit_cases": empty,
            "key_exact_cases": key_exact, "final_exact_cases": sum(r["correct"] for r in group),
            "false_positive_keys": false_positive_keys, "false_negative_keys": false_negative_keys,
        }
        text.append(f"| {LABELS[provider]} | {selected_count} | {true_positive} | "
                    f"{true_positive}/{expected_count} | {empty}/20 | {key_exact}/20 | "
                    f"{sum(r['correct'] for r in group)}/20 |")
    text += [
        "", "门控全 omit 也可能产生很高的换序稳定性，但不意味着正确。"
        "这是一种固定门控提示的实测，不代表所有两阶段设计都具有相同性能。", "",
        "## Liquid：24℃温度题", "",
    ]
    for case, provider, arms in (
        ("S03", "liquid", ["baseline", "combined", "two_stage"]),
        ("S01", "h2o", ["baseline", "criteria_only", "rules_only", "combined", "two_stage"]),
        ("M08", "h2o", ["baseline", "criteria_only", "rules_only", "combined", "two_stage"]),
        ("N03", "h2o", ["baseline", "rules_only", "combined", "two_stage"]),
        ("N04", "h2o", ["baseline", "rules_only", "combined", "two_stage"]),
        ("S03", "decider", ["baseline", "rules_only", "combined", "two_stage"]),
    ):
        if (case, provider) != ("S03", "liquid"):
            text += [f"## {LABELS[provider]}：{case}", ""]
        subset = [r for r in rows if r["provider"] == provider and r["case_id"] == case
                  and r["variant"] == "original" and r["arm"] in arms]
        text += ["> " + subset[0]["query"], "",
                 "参考：" + display_commands(subset[0]["expected"]), ""]
        for arm in arms:
            row = next(r for r in subset if r["arm"] == arm)
            text.append(f"- {arm}：{'正确' if row['correct'] else '错误'}，"
                        + display_commands(row["cmdList"]))
            if arm == "two_stage":
                text.append("  第一阶段选中：" + (", ".join(row["gate_selected_keys"] or []) or "无"))
        text.append("")
    text += [
        "## 如何查看完整请求和原始回答", "",
        "- [S03五组完整请求及问题改写](examples/S03.requests.zh.md)。JSON中的state包含完整30项Command Set。",
        "- [S03三个模型五组实际输出](examples/S03.actual_outputs.json)：包括参考、实际cmdList、多余/缺失与门控Key。",
        "- [S03原始HTTP阶段记录](examples/S03.raw_http.json)：包括每一步实际payload、原始response_text、"
        "解析response、概率及计时。历史基线记录与本轮记录用source字段区分。",
        "- [N04 H2O反例的全部实际请求与回答](examples/N04.h2o.raw_http.json)："
        "包括基线、三个改写组和两阶段的完整问题及候选。",
        "- [完整对照报告](ABLATION.zh.md)、[门控诊断数据](gate_diagnostics.json)。",
        "",
    ]
    save(run / "gate_diagnostics.json", diagnostics)
    examples = run / "examples"
    examples.mkdir(exist_ok=True)
    save(examples / "S03.actual_outputs.json",
         [r for r in rows if r["case_id"] == "S03" and r["variant"] == "original"])
    plan = json.loads((run / "plan.json").read_text())
    baseline_example = next(
        e["first_payload"] for e in json.loads((run / "experiments.json").read_text())
        if e["case_id"] == "S03" and e["variant"] == "original" and e["arm"] == "baseline"
    )
    records = []
    for provider in MODEL_IDS:
        for label, source in (
            ("historical_baseline", Path(__file__).resolve().parent / plan["baseline_files"][provider]),
            ("new_formal", run / provider / "formal_receipts.jsonl"),
        ):
            for line in source.read_text().splitlines():
                row = json.loads(line)
                if row["case_id"] == "S03" and row["variant"] == "original":
                    record = {"source": label, "provider": provider, "receipt": row}
                    if label == "historical_baseline":
                        record["payload_from_frozen_baseline"] = baseline_example
                    records.append(record)
    save(examples / "S03.raw_http.json", records)
    save(examples / "N04.h2o.raw_http.json", [
        row for line in (run / "h2o/formal_receipts.jsonl").read_text().splitlines()
        if (row := json.loads(line))["case_id"] == "N04"
    ])
    (run / "DIAGNOSTICS.zh.md").write_text("\n".join(text))
    print(json.dumps(diagnostics, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    diagnose(parser.parse_args().run)
