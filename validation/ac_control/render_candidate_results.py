"""Render completed measurements and export full, inspectable request/answer examples."""

import json
from pathlib import Path

from analyze_candidates import analyze

NAMES = {"pplx": "Perplexity Flash", "knowline": "KnowLine Gen5.5",
         "torchcast": "Torchcast", "clef": "Clef-Flash", "h2o": "H2O"}


def render(root):
    summary = analyze(root)
    refs = {r["id"]: r for r in json.loads((root / "references.json").read_text())}
    text = ["# 独占 L4 候选扩展测试原始结果", "",
            "规范验收主成绩只计原序 20 题，见[七模型统一对照]"
            "(../../../../docs/AC_SPEC_UNIFIED_RESULTS.md)。以下 156 次为扩展观察，单独保留。", "",
            "每模型 156 次质量请求；中文是 24 条英文新题的对应翻译，两种候选顺序分别计分。"
            "正确要求整组动作完全匹配，不修复模型答案。", "",
            "| 模型 | 状态 | 英文 | 中文 | 总计 | 选项换序后选择改变 |",
            "|---|---|---:|---:|---:|---:|"]
    for name, model in summary["models"].items():
        if model["status"] != "complete":
            text.append(f"| {NAMES[name]} | {model['status']} | — | — | — | — |")
            continue
        scores = model["scores"]
        values = [f"{scores[key]['correct']}/{scores[key]['requests']}" for key in ("en", "zh", "all")]
        text.append(f"| {NAMES[name]} | complete | " + " | ".join(values)
                    + f" | {len(model['option_order_changed_cases'])}/78 |")
    text += ["", "Clef 官方编码器会按选项 ID 排序，因此反转传入字典后模型仍看到相同候选顺序；"
             "它的 0/78 表示原生接口结果稳定，不能作为权重抵抗候选位置变化的证据。", "",
             "## 预热后延迟", "",
             "S03 每模式三轮。时间为收到选择的耗时，不表示答案正确；下面另列封装导致的选择变化。"
             "不同指令均值包含原序和反序请求，缓存策略仍保留作者实现。", "",
             "| 模型 | 单字段均值 ms | 30 步串行均值 s | 串行最小–最大 s | 完整 30 题均值 s | 156 条质量请求均值 s |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, model in summary["models"].items():
        if model["status"] != "complete":
            continue
        latency = model["latency"]
        serial = latency["serial30_total_ms"]
        text.append(f"| {NAMES[name]} | {latency['single_key_ms']['mean']:.2f} | {serial['mean']/1000:.3f}"
                    f" | {serial['min']/1000:.3f}–{serial['max']/1000:.3f}"
                    f" | {latency['full30_ms']['mean']/1000:.3f}"
                    f" | {model['scores']['all']['client_ms']['mean']/1000:.3f} |")
    for name, model in summary["models"].items():
        if model["status"] != "complete":
            continue
        text += ["", "## " + NAMES[name], "",
                 f"正式调用 {model['formal_calls']}，HTTP 预热 {model['warmup_calls']}，"
                 f"接口/格式错误 {model['errors']}。", "",
                 "| 数据集 | 原顺序 | 反顺序 |", "|---|---:|---:|"]
        for dataset, label in (("spec", "英文规范"), ("extension", "英文诊断"),
                               ("validation", "英文新增"), ("chinese", "中文翻译")):
            values = [model["scores"][dataset + ":" + order] for order in ("original", "reversed")]
            text.append(f"| {label} | " + " | ".join(f"{v['correct']}/{v['requests']}" for v in values) + " |")
        text += ["", "S03 串行与完整请求的选择比较：", ""]
        for row in model["s03_layout_comparison"]:
            text.append(f"- 第 {row['repetition'] + 1} 轮：改变字段 {row['changed_fields'] or '无'}；"
                        f"串行正确={row['serial_correct']}，完整正确={row['full_correct']}。")
        text += ["", "原顺序错误案例：", ""]
        for row in model["rows"]:
            if row["order"] == "original" and not row["correct"]:
                text.append(f"- {row['case_id']}：多余 {row['extra'] or '无'}；遗漏 {row['missing'] or '无'}。")
        calls = [json.loads(line) for line in (root / "results" / name / "receipts.jsonl").read_text().splitlines()]
        for row in calls:
            if row["kind"] != "quality" or row["order"] != "original" or row["case_id"] not in ("S03", "N10", "Z05", "H20"):
                continue
            target = root / "examples" / (name + "-" + row["case_id"] + ".json")
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps({
                "expected_local_only": refs[row["case_id"]]["expected"],
                "full_request_and_native_response": row,
            }, ensure_ascii=False, indent=2) + "\n")
    text += ["", "完整请求、所有选项和原始回答示例见 [examples](examples/)。"
             "全部逐题评分见 [summary.json](summary.json)，原始证据见 [results](results/)。", ""]
    (root / "RESULTS.zh.md").write_text("\n".join(text))


if __name__ == "__main__":
    render(Path(__file__).parent / "runs/2026-10-30-candidates-l4-v1")
