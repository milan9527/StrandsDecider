"""Strict offline scoring; never repair model selections using expected answers."""

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

from prepare import OMIT, save, sha


def pairs(commands):
    return {(c["cmdKey"], str(c["cmdValue"])) for c in commands}


def decode(response, request, capabilities):
    if response.get("model") != "strands-decider-2B-hobson-v19-vllm":
        raise ValueError("Unexpected model")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
        raise ValueError("Response must answer exactly the supplied questions")
    commands, choices = [], {}
    catalog = {c["key"]: c for c in capabilities["commandSet"]}
    for key, question in request["questions"].items():
        answer = answers[key]
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise ValueError(f"{key}: expected a choice answer")
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in question["criteria"]:
            raise ValueError(f"{key}: selection outside supplied candidates")
        choices[key] = choice
        if choice != OMIT:
            commands.append({
                "cmdName": catalog[key]["name"], "cmdKey": key, "cmdValue": choice,
            })
    return commands, choices


def grade(expected, actual, status="ok"):
    expected_pairs, actual_pairs = pairs(expected), pairs(actual)
    expected_keys = {k for k, _ in expected_pairs}
    actual_keys = {k for k, _ in actual_pairs}
    return {
        "correct": status == "ok" and actual_pairs == expected_pairs,
        "keys_correct": status == "ok" and actual_keys == expected_keys,
        "expected_count": len(expected_pairs),
        "predicted_count": len(actual_pairs),
        "correct_pairs": len(expected_pairs & actual_pairs),
        "correct_keys": len(expected_keys & actual_keys),
        "extra": sorted(actual_pairs - expected_pairs),
        "missing": sorted(expected_pairs - actual_pairs),
        "extra_keys": sorted(actual_keys - expected_keys),
        "missing_keys": sorted(expected_keys - actual_keys),
        "wrong_values": sorted(
            k for k in expected_keys & actual_keys
            if {v for key, v in actual_pairs if key == k}
            != {v for key, v in expected_pairs if key == k}
        ),
    }


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def timing(values):
    values = sorted(v for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    if not values:
        return {"count": 0}
    return {
        "count": len(values), "mean": statistics.mean(values),
        "p50": statistics.median(values), "p95": values[math.ceil(0.95 * len(values)) - 1],
        "min": values[0], "max": values[-1], "total": sum(values),
    }


def summarize(rows):
    expected = sum(r["expected_count"] for r in rows)
    predicted = sum(r["predicted_count"] for r in rows)
    correct = sum(r["correct_pairs"] for r in rows)
    keys = sum(r["correct_keys"] for r in rows)
    return {
        "cases": len(rows),
        "errors": sum(r["status"] != "ok" for r in rows),
        "exact_match": ratio(sum(r["correct"] for r in rows), len(rows)),
        "single_exact": ratio(
            sum(r["correct"] for r in rows if r["category"] == "single"),
            sum(r["category"] == "single" for r in rows),
        ),
        "multi_exact": ratio(
            sum(r["correct"] for r in rows if r["category"] == "multi"),
            sum(r["category"] == "multi" for r in rows),
        ),
        "key_set_exact": ratio(sum(r["keys_correct"] for r in rows), len(rows)),
        "key_precision": ratio(keys, predicted),
        "key_recall": ratio(keys, expected),
        "value_accuracy_given_correct_key": ratio(correct, keys),
        "pair_precision": ratio(correct, predicted),
        "pair_recall": ratio(correct, expected),
        "extra_command_rate": ratio(predicted - correct, predicted),
        "missing_command_rate": ratio(expected - correct, expected),
        "cases_with_extra": sum(bool(r["extra"]) for r in rows),
        "cases_with_missing": sum(bool(r["missing"]) for r in rows),
        "server_ms": timing(r.get("server_ms") for r in rows if r["status"] == "ok"),
        "client_ms": timing(r["client_ms"] for r in rows),
    }


def display_ratio(value):
    if value["rate"] is None:
        return "N/A"
    return f'{value["numerator"]}/{value["denominator"]}（{value["rate"]:.1%}）'


def display_commands(commands):
    return ", ".join(f"`{k}={v}`" for k, v in sorted(pairs(commands))) or "∅"


def report(run, summary, rows):
    original, reversed_ = summary["original"], summary["reversed"]
    environment_note = "本轮只向 Decider 发出测试推理请求。"
    if (run / "environment.json").exists():
        environment = json.loads((run / "environment.json").read_text())
        environment_note += (
            f" AWS 核验实例为 `{environment['InstanceId']}` / "
            f"`{environment['InstanceType']}` / "
            f"`{environment['Placement']['AvailabilityZone']}`。"
            "GPU 与共享服务状态见环境快照。"
        )
    text = [
        "# 空调控制：Strands Decider 实测",
        "",
        f"正式测试时间：{summary['started_at']}。"
        f"原始候选顺序完全匹配 **{display_ratio(original['exact_match'])}**；"
        f"反转候选顺序完全匹配 **{display_ratio(reversed_['exact_match'])}**。",
        "",
        "模型为已部署的 `strands-decider-2B-hobson-v19-vllm`，"
        "通过现有 HTTPS `/v1/systemone` 调用。"
        "测试仅评估控制指令选择，没有向真实空调下发指令。",
        "",
        environment_note,
        "",
        "## 方法与边界",
        "",
        "- 从 [测试规范快照](spec.md) 自动提取 30 项完整 Command Set 和 20 条英文 Query。"
        "每次请求携带同一完整能力集；标准答案仅用于离线评分。",
        "- 每个 Key 对应一个独立 choice，候选为该 Key 的所有合法控制值及 `omit`（不下发）。"
        "一次 HTTP 请求包含 30 个问题；服务分别评估每个问题。"
        "模型每个非 omit 选择直接映射到 cmdList，程序不补电源、模式或温度单位，也不修正模型错误。",
        "- 保留标准 Command Set 的全部映射，包括自动除霜清洁状态值 2–4；"
        "它们按规范不进入可下发候选。范围字段枚举整个合法整数区间，"
        "并保留原始 min/max；本批 Query 均为整数，没有验证小数控制。",
        "- 原顺序为 omit 在前、其余值按规范排列；反转顺序仅反转每题候选，Query、完整能力集、问题顺序及说明不变。"
        "两组是同一批 20 条用例的重复观察，不能当作 40 条独立样本。",
        "- 正式测试单客户端串行调用，不自动重试。预检请求独立保存在 `probe_*`，不计入准确率与正式耗时。",
        "- `server_ms` 来自服务返回的 `latency_ms`，包含预处理、排队及这 30 个问题的处理；"
        "`client_ms` 另含 HTTPS 网络往返。两者均不是纯 GPU 计算时间。",
        "- 合法 Key/Value 由候选空间约束；合法率高不等于语义选择正确。"
        "本规范未覆盖否定、越界、冲突指令等反例，不能据此推断生产可靠性。",
        "",
        "## 指标",
        "",
        "| 指标 | 原始顺序（主结果） | 反转顺序（稳定性） |",
        "|---|---:|---:|",
    ]
    for label, key in [
        ("全部完全匹配", "exact_match"), ("单指令完全匹配", "single_exact"),
        ("多指令完全匹配", "multi_exact"), ("Key 集合完全匹配", "key_set_exact"),
        ("Key 精确率", "key_precision"), ("Key 召回率", "key_recall"),
        ("已选对 Key 中 Value 准确率", "value_accuracy_given_correct_key"),
        ("Key/Value 对精确率", "pair_precision"), ("Key/Value 对召回率", "pair_recall"),
        ("多余指令比例", "extra_command_rate"), ("缺失指令比例", "missing_command_rate"),
    ]:
        text.append(f"| {label} | {display_ratio(original[key])} | {display_ratio(reversed_[key])} |")
    text += [
        f"| 调用/格式失败 | {original['errors']} | {reversed_['errors']} |",
        "",
        "完全匹配按无序 `cmdKey/cmdValue` 集合比较。Key 精确率=正确 Key 数/预测指令数；"
        "Key 召回率=正确 Key 数/参考指令数。Value 准确率仅以已匹配 Key 为分母，"
        "应与 Key 召回率一起看。多余=预测集合减参考集合，占预测指令数；"
        "缺失=参考集合减预测集合，占参考指令数。Value 错误同时形成一个多余对和一个缺失对。"
        "调用/格式失败计为该用例不匹配，并按参考指令全部缺失计分。",
        "",
        f"候选换序后输出改变：**{summary['changed_cases']}/{summary['valid_order_pairs']}**"
        "（仅比较两次均有效的成对请求）。",
        "",
        "## 耗时（每条 Query 的全部 30 个问题，毫秒）",
        "",
        "| 测量 | 组别 | 平均 | P50 | P95 | 最小–最大 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for variant, label in [("original", "原始"), ("reversed", "反转")]:
        for key, measurement in [("server_ms", "服务端"), ("client_ms", "客户端")]:
            value = summary[variant][key]
            if value["count"]:
                text.append(
                    f"| {measurement} | {label} | {value['mean']:.1f} | {value['p50']:.1f} | "
                    f"{value['p95']:.1f} | {value['min']:.1f}–{value['max']:.1f} |"
                )
    text += [
        "", "## 逐例结果", "",
        "| 用例 | 参考 cmdList | 原始顺序实际 cmdList | 原始 | 反转 |",
        "|---|---|---|---|---|",
    ]
    lookup = {(r["case_id"], r["variant"]): r for r in rows}
    for row in rows:
        if row["variant"] != "original":
            continue
        other = lookup[row["case_id"], "reversed"]
        text.append(
            f"| {row['case_id']} {row['title']} | {display_commands(row['expected'])} | "
            f"{display_commands(row['cmdList'])} | {'通过' if row['correct'] else '失败'} | "
            f"{'通过' if other['correct'] else '失败'} |"
        )
    text += ["", "## 失败详情", ""]
    for row in rows:
        if row["correct"]:
            continue
        text += [
            f"### {row['case_id']} / {row['variant']}",
            "",
            f"> {row['query']}",
            "",
            f"- 预期：{display_commands(row['expected'])}",
            f"- 实际：{display_commands(row['cmdList'])}",
            f"- 多余：{', '.join(f'`{k}={v}`' for k, v in row['extra']) or '无'}",
            f"- 缺失：{', '.join(f'`{k}={v}`' for k, v in row['missing']) or '无'}",
            "",
        ]
        if row.get("error"):
            text += [f"错误：`{row['error']}`", ""]
    text += [
        "## 可复核证据", "",
        "- [冻结计划](plan.json)、[完整模型请求](requests.json)、[离线标准答案](references.json)。",
        "- [原始响应逐条记录](formal_receipts.jsonl)、[归一化逐例评分](results.json)、[指标](summary.json)。",
        "- [模型身份](formal_models.json)、[测试前健康](formal_health_before.json)、"
        "[测试后健康](formal_health_after.json)。",
        "- 完整复现步骤见 [测试目录说明](../../README.zh.md)。",
        "",
    ]
    if (run / "environment_live.json").exists():
        text += [
            "[EC2 实例核验](environment.json) · [GPU 与 systemd 实时快照](environment_live.json)",
            "",
        ]
    (run / "REPORT.zh.md").write_text("\n".join(text))


def analyze(run):
    plan = json.loads((run / "plan.json").read_text())
    cases = json.loads((run / "references.json").read_text())
    requests = json.loads((run / "requests.json").read_text())
    if sha(cases) != plan["references_sha256"] or sha(requests) != plan["requests_sha256"]:
        raise ValueError("Frozen evidence hash mismatch")
    capabilities = json.loads((run / "command_set.json").read_text())
    lookup = {(r["case_id"], r["variant"]): r for r in requests}
    references = {r["id"]: r for r in cases}
    receipts = [json.loads(line) for line in (run / "formal_receipts.jsonl").read_text().splitlines()]
    if len(receipts) != len(requests):
        raise ValueError("Formal run is incomplete")
    seen, rows = set(), []
    for receipt in receipts:
        identity = receipt["case_id"], receipt["variant"]
        if identity in seen:
            raise ValueError("Duplicate formal observation")
        seen.add(identity)
        request = lookup[identity]
        if receipt["input_sha256"] != sha(request["payload"]):
            raise ValueError("Receipt/request hash mismatch")
        reference = references[receipt["case_id"]]
        row = {
            "case_id": identity[0], "variant": identity[1], "title": reference["title"],
            "query": reference["query"], "category": reference["category"],
            "expected": reference["expected"], "status": receipt["status"],
            "cmdList": [], "client_ms": receipt["client_ms"],
            "server_ms": receipt.get("response", {}).get("latency_ms"),
            "input_sha256": receipt["input_sha256"],
        }
        if row["status"] == "ok":
            try:
                row["cmdList"], row["choices"] = decode(
                    receipt["response"], request["payload"], capabilities
                )
            except ValueError as error:
                row.update(status="format_error", error=str(error))
        else:
            row["error"] = receipt.get("error", receipt.get("response_text", "Request failed"))
        row.update(grade(row["expected"], row["cmdList"], row["status"]))
        rows.append(row)
    by_identity = {(r["case_id"], r["variant"]): r for r in rows}
    order_pairs = [
        (by_identity[c["id"], "original"], by_identity[c["id"], "reversed"])
        for c in cases
        if all(by_identity[c["id"], v]["status"] == "ok" for v in ("original", "reversed"))
    ]
    summary = {
        "started_at": json.loads((run / "formal_run.json").read_text())["started_at"],
        "original": summarize([r for r in rows if r["variant"] == "original"]),
        "reversed": summarize([r for r in rows if r["variant"] == "reversed"]),
        "changed_cases": sum(pairs(a["cmdList"]) != pairs(b["cmdList"]) for a, b in order_pairs),
        "valid_order_pairs": len(order_pairs),
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "receipts_sha256": hashlib.sha256((run / "formal_receipts.jsonl").read_bytes()).hexdigest(),
    }
    save(run / "results.json", rows)
    save(run / "summary.json", summary)
    report(run, summary, rows)
    for variant in ("original", "reversed"):
        print(variant, display_ratio(summary[variant]["exact_match"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    analyze(parser.parse_args().run)
