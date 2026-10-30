"""Score resident-model observations with the original AC grading rules."""

import argparse
import hashlib
import json
from pathlib import Path

from analyze import display_commands, display_ratio, grade, pairs, summarize
from prepare import OMIT, save, sha
from run_resident import MODELS

MODEL_IDS = {"decider": "strands-decider-2B-hobson-v19-vllm",
             **{k: v["id"] for k, v in MODELS.items()}}
LABELS = {"decider": "Strands Decider v19", "liquid": "Liquid d1-2B", "h2o": "H2O Lightning 4B"}


def decode_model(response, request, catalog, model):
    if response.get("model") != model:
        raise ValueError("Unexpected model identity")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
        raise ValueError("Expected exactly the supplied question IDs")
    commands = []
    for key, question in request["questions"].items():
        answer = answers[key]
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise ValueError(f"{key}: expected a typed choice")
        selected = answer.get("choice")
        if not isinstance(selected, str) or selected not in question["criteria"]:
            raise ValueError(f"{key}: invalid candidate")
        if selected != OMIT:
            commands.append({
                "cmdName": catalog[key]["name"], "cmdKey": key, "cmdValue": selected,
            })
    return commands


def read_rows(path, provider, requests, references, capabilities, required_count=40):
    receipts = [json.loads(line) for line in path.read_text().splitlines()]
    if len(receipts) != required_count:
        raise ValueError(f"{path}: expected {required_count} receipts")
    catalog = {c["key"]: c for c in capabilities["commandSet"]}
    seen, rows = set(), []
    for receipt in receipts:
        identity = receipt["case_id"], receipt["variant"]
        if identity in seen:
            raise ValueError("Duplicate observation")
        seen.add(identity)
        request = requests[identity]
        if receipt["input_sha256"] != sha(request["payload"]):
            raise ValueError("Input differs from the frozen Decider baseline")
        reference = references[identity[0]]
        response = receipt.get("response", {})
        if response and json.loads(receipt["response_text"]) != response:
            raise ValueError("Parsed response differs from raw HTTP body")
        server_ms = response.get("latency_ms")
        if server_ms is None:
            server_ms = response.get("usage", {}).get("latency_ms")
        row = {
            "provider": provider, "case_id": identity[0], "variant": identity[1],
            "title": reference["title"], "query": reference["query"],
            "category": reference["category"], "expected": reference["expected"],
            "cmdList": [], "status": receipt["status"], "client_ms": receipt["client_ms"],
            "server_ms": server_ms, "input_sha256": receipt["input_sha256"],
        }
        if row["status"] == "ok":
            try:
                row["cmdList"] = decode_model(
                    response, request["payload"], catalog, MODEL_IDS[provider],
                )
            except ValueError as error:
                row.update(status="format_error", error=str(error))
        else:
            row["error"] = receipt.get("error", receipt.get("response_text", "Request failed"))
        row.update(grade(row["expected"], row["cmdList"], row["status"]))
        rows.append(row)
    return rows


def report(output, baseline, summary, rows, references):
    baseline_link = "../" + baseline.name
    text = [
        "# 空调控制：Decider、Liquid、H2O 同输入比较",
        "",
        "Liquid 和 H2O 使用现有 GPU 常驻服务新增实测；"
        "Strands Decider 复用同日较早完成的 40 次基线调用。"
        "每模型的主结果均为规范中的 20 条 Query，另外反转候选顺序各测 20 次。",
        "",
        "## 完全匹配",
        "",
        "| 模型 | 单指令 /10 | 多指令 /10 | 原始顺序 /20 | 反转顺序 /20 | 换序后改变 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for provider in MODEL_IDS:
        model = summary["models"][provider]
        primary = model["original"]
        text.append(
            f"| {LABELS[provider]} | {display_ratio(primary['single_exact'])} | "
            f"{display_ratio(primary['multi_exact'])} | {display_ratio(primary['exact_match'])} | "
            f"{display_ratio(model['reversed']['exact_match'])} | "
            f"{model['changed_cases']}/{model['valid_order_pairs']} |"
        )
    text += [
        "", "## 指令指标（原始候选顺序）", "",
        "| 模型 | Key 精确率 | Key 召回率 | 已匹配 Key 的 Value 准确率 | 多余指令 | 缺失指令 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for provider in MODEL_IDS:
        model = summary["models"][provider]["original"]
        values = [display_ratio(model[key]) for key in [
            "key_precision", "key_recall", "value_accuracy_given_correct_key",
            "extra_command_rate", "missing_command_rate",
        ]]
        text.append(f"| {LABELS[provider]} | " + " | ".join(values) + " |")
    text += [
        "",
        "完全匹配比较无序 `cmdKey/cmdValue` 集合。Key 精确率=匹配 Key 数/预测指令数，"
        "Key 召回率=匹配 Key 数/参考指令数；Value 准确率以已匹配 Key 为分母。"
        "多余=预测集合减参考集合/预测指令数；缺失=参考集合减预测集合/参考指令数。"
        "错 Value 会同时产生一个多余对和一个缺失对。调用或格式失败留在分母。",
        "",
        "## 耗时与调用状态",
        "",
        "每条 Query 一次 HTTP 请求、30 个 choice。下列单位均为毫秒。",
        "",
        "| 模型 | 顺序 | 服务端平均 | 服务端 P50 | 服务端 P95 | 客户端平均 | 调用/格式失败 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for provider in MODEL_IDS:
        for variant in ("original", "reversed"):
            model = summary["models"][provider][variant]
            server, client = model["server_ms"], model["client_ms"]
            values = [f"{server[k]:.1f}" if server["count"] else "N/A" for k in ["mean", "p50", "p95"]]
            values.append(f"{client['mean']:.1f}" if client["count"] else "N/A")
            text.append(f"| {LABELS[provider]} | {variant} | " + " | ".join(values) + f" | {model['errors']} |")
    text += [
        "",
        "Decider/Liquid 的服务端计时读取顶层 `latency_ms`，H2O 读取 `usage.latency_ms`；"
        "各模型包装服务的计时边界不完全相同，均不能当作纯 GPU 计算时间。"
        "Decider 客户端包含 HTTPS 往返，Liquid/H2O 客户端位于 GPU 主机、走 loopback，"
        "因此不直接比较客户端延迟。Decider 为同日早先记录，未在本轮重新调用。",
        "",
        "## 完整输入与运行方法",
        "",
        "- 完整复用 Decider 基线中的 40 份请求，逐项核验包含候选顺序的 SHA-256。"
        "没有改写 Query、说明、30 项 Command Set 或候选。",
        "- 原生每 Key 一个 choice，候选为该 Key 的全部合法控制值及 omit。"
        "数值范围覆盖所有合法整数；每条实际请求均包含 30 问。"
        "5 条温度用例的单位也必须由模型独立选择，程序不补齐。",
        "- 业务网关限制 16 问/32 候选，本轮在 GPU 内直接调用现有 "
        "`127.0.0.1:18801`（Liquid）及 `127.0.0.1:18803`（H2O）原生服务。"
        "没有拆题、缩减候选、改服务配置或重新加载模型。",
        "- 现有实例 `i-0ae7eb0abcb815af3` / g6.xlarge / NVIDIA L4；三模型同卡常驻。"
        "Liquid 为官方 Transformers、BF16；H2O 为官方补丁 vLLM 0.30.0、FP8。"
        "分别串行跑完 Liquid 和 H2O，不并发压测。",
        "- 每个新模型各一次预检、40 次正式调用，不自动重试。"
        "预检与文件传输失败不计入正式推理准确率或耗时。",
        "- 只评估指令选择，不向真实空调下发。两种候选顺序是同一批 20 例的重复观察；"
        "结果只代表本套输入及运行方式，没有覆盖越界、小数、冲突与否定等反例。",
        "",
        "## 逐例实际输出（原始候选顺序）",
        "",
        "✓ 表示完整集合与参考相同；✗ 表示至少有一条多余、缺失或错误指令。",
        "",
        "| 用例 | 参考 | Decider | Liquid | H2O |",
        "|---|---|---|---|---|",
    ]
    lookup = {(r["provider"], r["case_id"], r["variant"]): r for r in rows}
    for reference in references.values():
        case_id = reference["id"]
        values = []
        for provider in MODEL_IDS:
            row = lookup[provider, case_id, "original"]
            values.append(("✓ " if row["correct"] else "✗ ") + display_commands(row["cmdList"]))
        text.append(
            f"| {case_id} {reference['title']} | {display_commands(reference['expected'])} | "
            + " | ".join(values) + " |"
        )
    text += ["", "## 新模型失败详情（两种候选顺序）", ""]
    for row in rows:
        if row["provider"] == "decider" or row["correct"]:
            continue
        text += [
            f"### {LABELS[row['provider']]} / {row['case_id']} / {row['variant']}",
            "", f"> {row['query']}", "",
            f"- 预期：{display_commands(row['expected'])}",
            f"- 实际：{display_commands(row['cmdList'])}",
            f"- 多余：{', '.join(f'`{k}={v}`' for k, v in row['extra']) or '无'}",
            f"- 缺失：{', '.join(f'`{k}={v}`' for k, v in row['missing']) or '无'}",
            "",
        ]
        if row.get("error"):
            text += [f"错误：`{row['error']}`", ""]
    text += [
        "## 证据与复现", "",
        f"- [共同请求]({baseline_link}/requests.json)、[共同标准答案]({baseline_link}/references.json)、"
        f"[Decider 基线报告]({baseline_link}/REPORT.zh.md)。",
        "- [比较计划](comparison_plan.json)、[指标](comparison_summary.json)、"
        "[逐条评分](comparison_results.json)。",
        "- [Liquid 原始返回](liquid/formal_receipts.jsonl)、[H2O 原始返回](h2o/formal_receipts.jsonl)。",
        "- [运行前环境](formal_before_environment.json)、[运行后环境](formal_after_environment.json)。",
        "- [Liquid 健康](liquid/formal_health_after.json)、[H2O 健康](h2o/formal_health_after.json)。",
        "- [测试代码与复现说明](../../README.zh.md)。", "",
    ]
    (output / "COMPARISON.zh.md").write_text("\n".join(text))


def compare(args):
    baseline = args.baseline
    plan = json.loads((baseline / "plan.json").read_text())
    request_list = json.loads((baseline / "requests.json").read_text())
    reference_list = json.loads((baseline / "references.json").read_text())
    if sha(request_list) != plan["requests_sha256"] or sha(reference_list) != plan["references_sha256"]:
        raise ValueError("Original frozen baseline changed")
    requests = {(r["case_id"], r["variant"]): r for r in request_list}
    references = {r["id"]: r for r in reference_list}
    capabilities = json.loads((baseline / "command_set.json").read_text())
    rows, summary = [], {"models": {}, "input_sha256": plan["requests_sha256"],
                         "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for provider in MODEL_IDS:
        directory = baseline if provider == "decider" else args.run / provider
        metadata = json.loads((directory / "formal_run.json").read_text())
        if metadata.get("status") != "complete" or metadata.get("actual_calls") != 40:
            raise ValueError(f"{provider}: formal run not complete")
        if metadata["requests_sha256"] != plan["requests_sha256"]:
            raise ValueError(f"{provider}: inputs differ")
        path = directory / "formal_receipts.jsonl"
        group = read_rows(path, provider, requests, references, capabilities)
        rows.extend(group)
        paired = {(r["case_id"], r["variant"]): r for r in group}
        valid_pairs = [
            (paired[c, "original"], paired[c, "reversed"]) for c in references
            if all(paired[c, v]["status"] == "ok" for v in ("original", "reversed"))
        ]
        summary["models"][provider] = {
            "model": MODEL_IDS[provider],
            **{v: summarize([r for r in group if r["variant"] == v])
               for v in ("original", "reversed")},
            "changed_cases": sum(pairs(a["cmdList"]) != pairs(b["cmdList"]) for a, b in valid_pairs),
            "valid_order_pairs": len(valid_pairs),
            "started_at": metadata["started_at"],
            "receipts_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    save(args.run / "comparison_results.json", rows)
    save(args.run / "comparison_summary.json", summary)
    report(args.run, baseline, summary, rows, references)
    for provider, model in summary["models"].items():
        print(provider, {v: display_ratio(model[v]["exact_match"]) for v in ["original", "reversed"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    compare(parser.parse_args())
