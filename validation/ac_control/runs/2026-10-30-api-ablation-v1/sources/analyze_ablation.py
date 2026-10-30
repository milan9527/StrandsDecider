"""Audit and score frozen prompt experiments, with no online answer repair."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from ablation_protocol import ARMS, selected_payload
from analyze import display_commands, display_ratio, grade, pairs, summarize
from compare_resident import LABELS, MODEL_IDS, read_rows
from prepare import save, sha
from run_ablation import choices

HERE = Path(__file__).resolve().parent
ARM_LABELS = {
    "baseline": "原始基线", "criteria_only": "仅改选项条件",
    "rules_only": "仅改规则与问题", "combined": "两项合并", "two_stage": "两阶段",
}


def complete_unit(commands, catalog):
    """Engineering metric only: never remove, replace or resolve conflicts."""
    result = copy.deepcopy(commands)
    keys = {c["cmdKey"] for c in result}
    scales = keys & {"t_temp", "t_temp_f"}
    if len(scales) == 1 and "t_temp_type" not in keys:
        result.append({
            "cmdName": catalog["t_temp_type"]["name"], "cmdKey": "t_temp_type",
            "cmdValue": "0" if "t_temp" in scales else "1",
        })
    return result


def decode_receipt(receipt, experiment, reference, catalog, provider):
    stages = receipt["stages"]
    if not stages or len(stages) > (2 if experiment["arm"] == "two_stage" else 1):
        raise ValueError("Unexpected number of HTTP stages")
    expected_payload, commands, gate_keys = experiment["first_payload"], [], None
    status = "ok"
    for index, stage in enumerate(stages):
        if expected_payload is None or sha(stage["payload"]) != sha(expected_payload):
            raise ValueError("Actual payload differs from frozen or model-selected payload")
        if stage["input_sha256"] != sha(stage["payload"]):
            raise ValueError("Stage payload hash mismatch")
        response = stage.get("response", {})
        if response and json.loads(stage["response_text"]) != response:
            raise ValueError("Raw and parsed response differ")
        if stage["status"] != "ok":
            status = stage["status"]
            if index != len(stages) - 1:
                raise ValueError("Continued after failed stage")
            break
        selected = choices(response, expected_payload, MODEL_IDS[provider])
        if selected != stage["choices"]:
            raise ValueError("Recorded choices differ from raw response")
        if experiment["arm"] == "two_stage" and index == 0:
            gate_keys = [k for k, v in selected.items() if v == "apply"]
            expected_payload = selected_payload(experiment["value_payload"], selected)
            if expected_payload is not None and len(stages) != 2:
                raise ValueError("Missing required value stage")
        else:
            commands = [
                {"cmdName": catalog[k]["name"], "cmdKey": k, "cmdValue": v}
                for k, v in selected.items() if v != "omit"
            ]
            expected_payload = None
    if receipt["status"] != status:
        raise ValueError("Observation status differs from stage status")
    if status != "ok":
        commands = []
    row = {
        **{k: receipt[k] for k in ("case_id", "dataset", "arm", "variant", "provider")},
        "query": reference["query"], "title": reference["title"], "category": reference["category"],
        "expected": reference["expected"], "cmdList": commands, "status": status,
        "client_ms": receipt["client_ms"], "server_ms": receipt["server_ms"],
        "http_calls": len(stages), "baseline_reused": False, "gate_selected_keys": gate_keys,
    }
    row.update(grade(row["expected"], commands, status))
    row["unit_completion_correct"] = grade(row["expected"], complete_unit(commands, catalog), status)["correct"]
    return row


def analyze(run, partial=False):
    plan = json.loads((run / "plan.json").read_text())
    experiments = json.loads((run / "experiments.json").read_text())
    references = json.loads((run / "references.json").read_text())
    cap = json.loads((run / "command_set.json").read_text())
    for key, value in (("experiments", experiments), ("references", references), ("command_set", cap)):
        if sha(value) != plan[key + "_sha256"]:
            raise ValueError("Frozen data changed: " + key)
    for name, checksum in plan["source_sha256"].items():
        if hashlib.sha256((run / "sources" / name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Frozen source changed: " + name)
    refs = {r["id"]: r for r in references}
    catalog = {c["key"]: c for c in cap["commandSet"]}
    lookup = {(e["case_id"], e["variant"], e["arm"]): e for e in experiments}
    baseline_requests = {
        (e["case_id"], e["variant"]): {"payload": e["first_payload"]}
        for e in experiments if e["reuse_baseline"]
    }
    rows, summary, evidence_hashes = [], {}, {}
    for provider in MODEL_IDS:
        baseline = HERE / plan["baseline_files"][provider]
        if hashlib.sha256(baseline.read_bytes()).hexdigest() != plan["baseline_sha256"][provider]:
            raise ValueError("Historical baseline changed")
        group = read_rows(baseline, provider, baseline_requests, refs, cap)
        for row in group:
            row.update(arm="baseline", dataset="spec", baseline_reused=True,
                       http_calls=1, gate_selected_keys=None)
            row["unit_completion_correct"] = grade(
                row["expected"], complete_unit(row["cmdList"], catalog), row["status"],
            )["correct"]
        path = run / provider / "formal_receipts.jsonl"
        receipts = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        if not partial:
            meta = json.loads((run / provider / "formal_run.json").read_text())
            if meta["status"] != "complete" or len(receipts) != plan["new_observations_per_model"]:
                raise ValueError(provider + ": incomplete formal run")
            if meta["actual_calls"] != sum(len(r["stages"]) for r in receipts):
                raise ValueError("Call count mismatch")
            if meta["experiments_sha256"] != plan["experiments_sha256"]:
                raise ValueError("Run metadata input mismatch")
        seen = set()
        for receipt in receipts:
            identity = receipt["case_id"], receipt["variant"], receipt["arm"]
            if identity in seen or lookup[identity]["reuse_baseline"] or receipt["provider"] != provider:
                raise ValueError("Duplicate, reused or wrong-provider observation")
            seen.add(identity)
            group.append(decode_receipt(receipt, lookup[identity], refs[identity[0]], catalog, provider))
        if path.exists():
            evidence_hashes[provider] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.extend(group)
        summary[provider] = {}
        for arm in ARMS:
            arm_rows = [r for r in group if r["arm"] == arm]
            statistics = {}
            for dataset, variant in (("spec", "original"), ("spec", "reversed"), ("extension", "original")):
                subset = [r for r in arm_rows if r["dataset"] == dataset and r["variant"] == variant]
                result = summarize(subset)
                result["unit_completion_exact_count"] = sum(r["unit_completion_correct"] for r in subset)
                result["http_calls"] = sum(r["http_calls"] for r in subset)
                result["gate_selected_key_count"] = sum(len(r["gate_selected_keys"] or []) for r in subset)
                statistics[dataset + "_" + variant] = result
            paired = {(r["case_id"], r["variant"]): r for r in arm_rows}
            order_pairs = [
                (paired[c, "original"], paired[c, "reversed"])
                for c in refs if all((c, v) in paired and paired[c, v]["status"] == "ok"
                                     for v in ("original", "reversed"))
            ]
            statistics.update(
                changed_cases=sum(pairs(a["cmdList"]) != pairs(b["cmdList"]) for a, b in order_pairs),
                valid_order_pairs=len(order_pairs),
            )
            baseline_lookup = {r["case_id"]: r for r in group
                               if r["arm"] == "baseline" and r["dataset"] == "spec" and r["variant"] == "original"}
            primary = [r for r in arm_rows if r["dataset"] == "spec" and r["variant"] == "original"]
            statistics["gained_vs_baseline"] = [r["case_id"] for r in primary
                                               if r["correct"] and not baseline_lookup[r["case_id"]]["correct"]]
            statistics["lost_vs_baseline"] = [r["case_id"] for r in primary
                                             if not r["correct"] and baseline_lookup[r["case_id"]]["correct"]]
            summary[provider][arm] = statistics
    result = {"partial": partial, "models": summary, "receipts_sha256": evidence_hashes,
              "observations": len(rows), "new_http_calls": sum(r["http_calls"] for r in rows if not r["baseline_reused"])}
    if not partial:
        save(run / "ablation_results.json", rows)
        save(run / "ablation_summary.json", result)
        report(run, result, rows, refs)
    for provider, model in summary.items():
        print(provider, {a: (display_ratio(s["spec_original"]["exact_match"]),
                             display_ratio(s["extension_original"]["exact_match"]))
                         for a, s in model.items()})
    return result, rows


def report(run, summary, rows, refs):
    text = [
        "# 空调控制：三个模型的提示词与两阶段对照实验", "",
        "主指标为原规范20条 Query 的整条指令集合完全匹配；任何多余、缺失或错值均失败。"
        "三个模型共五组，原规范各测原始与反转候选顺序。另测10条新表达/否定保持设置的诊断用例，单独统计。", "",
        "基线复用同日已有的每模型40次原始调用，新增10条诊断用例实测。其余组全部新增实测。"
        "所有 Query、完整30项能力集、合法候选范围和离线标准答案固定。"
        "提示词及诊断集在本轮推理前冻结，运行中不按结果调参。", "",
        "## 原规范完全匹配", "",
        "| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for provider, model in summary["models"].items():
        text.append("| " + LABELS[provider] + " | " + " | ".join(
            display_ratio(model[a]["spec_original"]["exact_match"]) for a in ARMS) + " |")
    text += [
        "", "仅改选项条件：将“Set Mode to Cool”等动作式描述改为“用户请求制冷”等意图匹配条件。"
        "仅改规则与问题：区分用户 Query 与能力目录，明确温度单位伴随字段、垂直摆风表示和独立功能。"
        "两项合并：同时采用上述改写。两阶段：第一步对30个 Key 选择 apply/omit，"
        "第二步只对模型选择的 Key 选择 Value，第二步仍有 omit。两个阶段都保留完整能力集。", "",
        "## 反转候选与稳定性", "",
        "| 模型 | 组别 | 原始顺序 | 反转顺序 | 换序后输出改变 | 原始多余对 | 原始缺失对 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for p, model in summary["models"].items():
        for a, stats in model.items():
            original = stats["spec_original"]
            text.append(f"| {LABELS[p]} | {ARM_LABELS[a]} | {display_ratio(original['exact_match'])} | "
                        f"{display_ratio(stats['spec_reversed']['exact_match'])} | "
                        f"{stats['changed_cases']}/{stats['valid_order_pairs']} | "
                        f"{original['extra_command_rate']['numerator']} | {original['missing_command_rate']['numerator']} |")
    text += ["", "## 新表达及反例（另计10条）", "",
             "这10条根据此前已见错误设计，在新调用前冻结，是诊断集，不是独立盲测集。"
             "覆盖“保持另一个设置不变”、相邻功能区别，以及新温度/负载数值；未覆盖冲突指令与越界数值。", "",
             "| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |",
             "|---|---:|---:|---:|---:|---:|"]
    for p, model in summary["models"].items():
        text.append("| " + LABELS[p] + " | " + " | ".join(
            display_ratio(model[a]["extension_original"]["exact_match"]) for a in ARMS) + " |")
    text += ["", "## 耗时、调用与单位补全", "",
             "耗时为原规范原始顺序下每条 Query 的服务端总耗时，"
             "两阶段累加实际发生的两次调用。统计边界依各模型服务实现，不能当作纯GPU时间。"
             "基线 Decider 客户端走HTTPS，本轮走GPU loopback，因此不比较客户端延迟。", "",
             "| 模型 | 组别 | 平均服务端 ms | P95 ms | HTTP调用 /20例 | 原始完全匹配 | 工程单位补全后 | 调用/格式失败 |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for p, model in summary["models"].items():
        for a, stats in model.items():
            s = stats["spec_original"]
            t = s["server_ms"]
            text.append(f"| {LABELS[p]} | {ARM_LABELS[a]} | {t.get('mean', 0):.1f} | "
                        f"{t.get('p95', 0):.1f} | {s['http_calls']} | "
                        f"{s['exact_match']['numerator']}/20 | {s['unit_completion_exact_count']}/20 | {s['errors']} |")
    text += ["", "工程单位补全是离线附加指标：仅当模型输出恰好一种温度字段且缺少单位时补充对应单位。"
             "不覆盖已有单位、不解决双温标冲突、不删除多余指令；不计入模型原始准确率。", "",
             f"正式新增HTTP调用：{summary['new_http_calls']}；观察数：{summary['observations']}（含120条历史基线）。"
             "没有自动重试，没有向真实空调下发指令。预检单独留存，不参与成绩。", "",
             "## 相对基线的修复与退步", "",
             "| 模型 | 组别 | 修复用例 | 退步用例 |", "|---|---|---|---|"]
    for p, model in summary["models"].items():
        for a in ARMS[1:]:
            s = model[a]
            text.append(f"| {LABELS[p]} | {ARM_LABELS[a]} | {', '.join(s['gained_vs_baseline']) or '无'} | "
                        f"{', '.join(s['lost_vs_baseline']) or '无'} |")
    lookup = {(r["provider"], r["case_id"], r["variant"], r["arm"]): r for r in rows}
    text += ["", "## 全部问题、参考与实际回答（原始顺序）", ""]
    for c, ref in refs.items():
        text += [f"### {c} {ref['title']}", "", f"> {ref['query']}", "",
                 "参考：" + display_commands(ref["expected"]), "",
                 "| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |",
                 "|---|---|---|---|---|---|"]
        for p in MODEL_IDS:
            cells = []
            for a in ARMS:
                r = lookup[p, c, "original", a]
                cells.append(("✓ " if r["correct"] else "✗ ") + display_commands(r["cmdList"]))
            text.append("| " + LABELS[p] + " | " + " | ".join(cells) + " |")
        text.append("")
    text += [
        "## 证据与边界", "",
        "- [冻结计划](plan.json)、[全部请求模板](experiments.json)、[离线参考](references.json)、"
        "[指标](ablation_summary.json)、[全部逐条评分](ablation_results.json)。",
        "- 原始HTTP请求/回答：[Decider](decider/formal_receipts.jsonl)、"
        "[Liquid](liquid/formal_receipts.jsonl)、[H2O](h2o/formal_receipts.jsonl)。",
        "- [运行前环境](formal_before_environment.json)、[运行后环境](formal_after_environment.json)。",
        "- 既有 GPU 三模型同卡常驻；串行调用，未调整服务、权重、量化或加载状态。"
        "Decider/Liquid为BF16，H2O为FP8。模型与部署栈不同，结果代表这些部署配置。",
        "- 基线复用较早记录，可能有时间漂移；同一用例内轮换改写组执行顺序。"
        "只有20条规范题、10条针对性诊断题，不支持推断生产总体准确率。"
        "两种候选顺序不是40条独立样本；反转两阶段会同时反转门控与值候选，未拆分两者影响。",
        "- 所有数值候选覆盖完整合法整数范围；没有答案导向的缩减。"
        "两阶段增加门控上下文与一次可能的HTTP调用，不能把收益单独归因于某个词。",
        "",
    ]
    (run / "ABLATION.zh.md").write_text("\n".join(text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    analyze(args.run, args.partial)
