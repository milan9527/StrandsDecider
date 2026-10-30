"""Write five-model gate diagnostics, usage and full M08 examples after scoring."""

import argparse
import json
from collections import Counter
from pathlib import Path

from ablation_protocol import ARMS
from analyze import display_commands
from analyze_ablation import ARM_LABELS
from analyze_api_ablation import LABELS
from run_resident import save


def diagnose(run):
    summary = json.loads((run / "five_model_summary.json").read_text())
    if summary["partial"] or summary["observations"] != 1250:
        raise ValueError("A complete audited five-model result is required")
    rows = json.loads((run / "five_model_results.json").read_text())
    raw = {
        p: [json.loads(s) for s in (run / p / "formal_receipts.jsonl").read_text().splitlines()]
        for p in ("jev", "gpt")
    }
    remainder = run / "gpt/remainder_receipts.jsonl"
    if remainder.exists():
        raw["gpt"] += [json.loads(s) for s in remainder.read_text().splitlines()]
    text = [
        "# 五模型错误定位与完整请求示例", "",
        "以下内容由已完成评分的原始观察生成，不发起推理、不修改答案或评分。", "",
        "## 两阶段门控：原规范20题、原始候选顺序", "",
        "| 模型 | 选中Key | 其中正确 | 所需Key召回 | 全omit题数 | Key集合正确 | 最终指令正确 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    gates = {}
    for provider in LABELS:
        group = [r for r in rows if r["provider"] == provider and r["arm"] == "two_stage"
                 and r["dataset"] == "spec" and r["variant"] == "original"]
        counts = Counter()
        for row in group:
            selected = set(row["gate_selected_keys"] or [])
            expected = {c["cmdKey"] for c in row["expected"]}
            counts.update(
                selected=len(selected), true_positive=len(selected & expected),
                required=len(expected), empty=int(not selected),
                key_exact=int(selected == expected), final_exact=int(row["correct"]),
            )
        gates[provider] = dict(counts)
        text.append(f"| {LABELS[provider]} | {counts['selected']} | {counts['true_positive']} | "
                    f"{counts['true_positive']}/{counts['required']} | {counts['empty']}/20 | "
                    f"{counts['key_exact']}/20 | {counts['final_exact']}/20 |")
    text += [
        "", "门控漏选的Key不能由第二阶段补回；多选的Key仍可在第二阶段选omit。"
        "空选择虽然可能对候选换序稳定，但不代表正确。", "",
        "## Jev / GPT 全部错误观察", "",
        "每种候选顺序单独列出；原规范与新增诊断题仍分开计分。", "",
        "| 模型 | 用例 | 顺序 | 方案 | 参考 | 实际 | 状态 |",
        "|---|---|---|---|---|---|---|",
    ]
    failures = [r for r in rows if r["provider"] in raw and not r["correct"]]
    for row in failures:
        text.append(f"| {LABELS[row['provider']]} | {row['case_id']} | {row['variant']} | "
                    f"{ARM_LABELS[row['arm']]} | {display_commands(row['expected'])} | "
                    f"{display_commands(row['cmdList'])} | {row['status']} |")
    text += [
        "", "`capture_error`表示原始返回未能保存，实际答案未知，表中的∅仅为评分占位。"
        "它按失败留在分母，但不能解释为模型输出了空指令。", "",
    ]
    if not failures:
        text.append("| 两个新增模型 | 无错误 | — | — | — | — | — |")
    example = [r for r in rows if r["case_id"] == "M08" and r["variant"] == "original"]
    text += [
        "", "## M08：上下摆风与水平送风", "", "> " + example[0]["query"], "",
        "参考：" + display_commands(example[0]["expected"]), "",
        "这条Query要求开启上下摆风、水平向两侧送风。"
        "`t_up_down=1`已表达上下摆风，按规范不应再发等价的`t_swing_angle=0`。", "",
        "| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |",
        "|---|---|---|---|---|---|",
    ]
    for provider in LABELS:
        lookup = {r["arm"]: r for r in example if r["provider"] == provider}
        text.append("| " + LABELS[provider] + " | " + " | ".join(
            ("✓ " if lookup[a]["correct"] else "✗ ") + display_commands(lookup[a]["cmdList"])
            for a in ARMS) + " |")
    text += [
        "", "- [M08五组完整问题、选项及任务规则](examples/M08.requests.zh.md)："
        "state展开为JSON，保留完整30项能力及全部候选。",
        "- [M08五模型实际指令](examples/M08.actual_outputs.json)。",
        "- [M08 Jev与GPT实际请求和原始回答](examples/M08.api_raw.json)："
        "含GPT完整系统提示、modelId、low参数与SDK返回，以及两阶段实际选中的问题。", "",
        "## API返回的用量", "",
        "以下累计有完整记录的正式调用的原生usage字段，预检单独保存。"
        "丢失记录的1次调用无法获得usage，未纳入用量合计。"
        "两家API字段口径不同，不能直接据此比较价格。"
        "GPT命中缓存的输入token单列；延迟来自本轮实际API路径及缓存状态。", "",
        "| API | 正式调用数 | 原生usage合计 |",
        "|---|---:|---|",
    ]
    usage = {}
    for provider, receipts in raw.items():
        counts = Counter()
        calls = sum(len(r["stages"]) for r in receipts)
        for row in receipts:
            for stage in row["stages"]:
                counts.update({k: v for k, v in stage.get("response", {}).get("usage", {}).items()
                               if isinstance(v, (int, float))})
        usage[provider] = {"calls": calls, "usage": dict(counts)}
        text.append(f"| {LABELS[provider]} | {calls} | `{json.dumps(dict(counts))}` |")
    text += ["", "[五模型完整成绩、耗时及逐题回答](FIVE_MODELS.zh.md)。", ""]
    (run / "DIAGNOSTICS.zh.md").write_text("\n".join(text))
    save(run / "diagnostics.json", {"gates": gates, "api_failures": failures, "api_usage": usage})
    output = run / "examples"
    output.mkdir(exist_ok=True)
    save(output / "M08.actual_outputs.json", example)
    save(output / "M08.api_raw.json", [
        row for receipts in raw.values() for row in receipts
        if row["case_id"] == "M08" and row["variant"] == "original"
    ])
    experiments = [e for e in json.loads((run / "experiments.json").read_text())
                   if e["case_id"] == "M08" and e["variant"] == "original"]
    request_text = [
        "# M08：五组完整任务模板", "",
        "为便于阅读，下面把实际请求中字符串类型的state展开为JSON对象；内容未变。"
        "精确传输格式见[M08原始调用](M08.api_raw.json)。"
        "两阶段的第二步模板包含全部问题，实际只发送第一步模型选中的Key；"
        "完整30项能力集始终保留。", "",
    ]
    for experiment in experiments:
        request_text += ["## " + ARM_LABELS[experiment["arm"]], ""]
        for key in ("first_payload", "value_payload"):
            payload = experiment.get(key)
            if payload is None:
                continue
            request_text += [
                "第一步实际任务：" if key == "first_payload" else "第二步完整模板（实际按门控选择）：", "",
                "```json", json.dumps({**payload, "state": json.loads(payload["state"])},
                                     ensure_ascii=False, indent=2), "```", "",
            ]
    (output / "M08.requests.zh.md").write_text("\n".join(request_text))
    print(f"Wrote diagnostics: {len(failures)} API error observations, full M08 examples.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    diagnose(parser.parse_args().run)
