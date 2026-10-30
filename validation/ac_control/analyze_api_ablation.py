"""Strictly audit API additions and combine them with unchanged GPU observations."""

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path

from ablation_protocol import ARMS, selected_payload
from analyze import display_commands, display_ratio, grade, pairs, summarize
from analyze_ablation import ARM_LABELS, complete_unit
from analyze_ablation import analyze as analyze_previous
from api_ablation_protocol import GPT_MODEL, decode_gpt, decode_jev, gpt_request, jev_request
from compare_resident import LABELS as GPU_LABELS
from run_resident import save, sha

LABELS = {**GPU_LABELS, "jev": "Jev", "gpt": "GPT 6.1 Sol · low"}


def decode_receipt(receipt, experiment, reference, catalog, expected_model):
    provider = receipt["provider"]
    stages = receipt["stages"]
    if not stages or len(stages) > (2 if experiment["arm"] == "two_stage" else 1):
        raise ValueError("Unexpected HTTP stage count")
    expected_payload = experiment["first_payload"]
    commands, gate_keys, status = [], None, "ok"
    for index, stage in enumerate(stages):
        if expected_payload is None or sha(stage["payload"]) != sha(expected_payload):
            raise ValueError("Actual task payload differs from frozen/model-selected payload")
        if stage["input_sha256"] != sha(expected_payload):
            raise ValueError("Task payload hash mismatch")
        expected_transport = gpt_request(expected_payload) if provider == "gpt" else jev_request(expected_payload)
        if sha(stage["transport_request"]) != sha(expected_transport):
            raise ValueError("Provider request differs from frozen transport, model or effort")
        if stage["transport_sha256"] != sha(expected_transport):
            raise ValueError("Transport hash mismatch")
        expected_stage = "gate" if experiment["arm"] == "two_stage" and index == 0 else "value"
        if stage["stage"] != expected_stage:
            raise ValueError("Unexpected stage label")
        if stage["status"] != "ok":
            status = stage["status"]
            if index != len(stages) - 1:
                raise ValueError("Continued after failed stage")
            break
        response = stage["response"]
        native_server_ms = (response.get("latency_ms") if provider == "jev"
                            else response.get("metrics", {}).get("latencyMs"))
        if stage.get("server_ms") != native_server_ms or stage["http_status"] != 200:
            raise ValueError("Recorded server timing/status differs from native response")
        if provider == "jev":
            if json.loads(stage["response_text"]) != response:
                raise ValueError("Parsed response differs from raw HTTP")
            selected = decode_jev(response, expected_payload, expected_model)
            if stage["model_id"] != expected_model:
                raise ValueError("Wrong Jev identity")
        else:
            if stage["model_id"] != GPT_MODEL or response["ResponseMetadata"]["HTTPStatusCode"] != 200:
                raise ValueError("Wrong GPT model or failed response")
            if response["ResponseMetadata"].get("RetryAttempts", 0) != 0:
                raise ValueError("Unexpected SDK retry")
            selected = decode_gpt(response, expected_payload)
        if selected != stage["choices"]:
            raise ValueError("Recorded choices differ from native response")
        if expected_stage == "gate":
            gate_keys = [k for k, v in selected.items() if v == "apply"]
            expected_payload = selected_payload(experiment["value_payload"], selected)
            if expected_payload is not None and len(stages) != 2:
                raise ValueError("Missing required value stage")
        else:
            commands = [{"cmdName": catalog[k]["name"], "cmdKey": k, "cmdValue": v}
                        for k, v in selected.items() if v != "omit"]
            expected_payload = None
    if status != receipt["status"]:
        raise ValueError("Observation status differs from stages")
    if receipt["client_ms"] != sum(s["client_ms"] for s in stages):
        raise ValueError("Client timing is not the sum of actual stages")
    times = [s.get("server_ms") for s in stages]
    server_ms = sum(times) if all(isinstance(v, (int, float)) for v in times) else None
    if receipt["server_ms"] != server_ms:
        raise ValueError("Server timing differs from stages")
    if status != "ok":
        commands = []
    row = {
        **{k: receipt[k] for k in ("provider", "case_id", "dataset", "variant", "arm")},
        "query": reference["query"], "title": reference["title"], "category": reference["category"],
        "expected": reference["expected"], "cmdList": commands, "status": status,
        "client_ms": receipt["client_ms"], "server_ms": receipt["server_ms"],
        "http_calls": len(stages), "baseline_reused": False, "gate_selected_keys": gate_keys,
    }
    row.update(grade(row["expected"], commands, status))
    row["unit_completion_correct"] = grade(
        row["expected"], complete_unit(commands, catalog), status,
    )["correct"]
    return row


def summarize_group(rows):
    results = {}
    for arm in ARMS:
        group = [r for r in rows if r["arm"] == arm]
        stats = {}
        for dataset, variant in (("spec", "original"), ("spec", "reversed"), ("extension", "original")):
            subset = [r for r in group if r["dataset"] == dataset and r["variant"] == variant]
            values = summarize(subset)
            values["unit_completion_exact_count"] = sum(r["unit_completion_correct"] for r in subset)
            values["http_calls"] = sum(r["http_calls"] for r in subset)
            stats[dataset + "_" + variant] = values
        lookup = {(r["case_id"], r["variant"]): r for r in group}
        valid_pairs = [
            (lookup[c, "original"], lookup[c, "reversed"])
            for c in {r["case_id"] for r in group if r["dataset"] == "spec"}
            if all((c, v) in lookup and lookup[c, v]["status"] == "ok" for v in ("original", "reversed"))
        ]
        stats["changed_cases"] = sum(pairs(a["cmdList"]) != pairs(b["cmdList"]) for a, b in valid_pairs)
        stats["valid_order_pairs"] = len(valid_pairs)
        results[arm] = stats
    return results


def analyze(run, partial=False):
    plan = json.loads((run / "plan.json").read_text())
    parent = Path(plan["parent_run"])
    for name, checksum in plan["parent_files_sha256"].items():
        if hashlib.sha256((parent / name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Previous evidence changed: " + name)
    for name, checksum in plan["source_sha256"].items():
        for source in (run / "sources" / name, Path(__file__).with_name(name)):
            if hashlib.sha256(source.read_bytes()).hexdigest() != checksum:
                raise ValueError("Frozen source changed: " + str(source))
    inputs = {}
    for name in ("experiments", "references", "command_set"):
        inputs[name] = json.loads((run / (name + ".json")).read_text())
        if sha(inputs[name]) != plan[name + "_sha256"]:
            raise ValueError("Frozen data changed: " + name)
    with contextlib.redirect_stdout(io.StringIO()):
        _, prior = analyze_previous(parent, partial=True)
    if sha(prior) != sha(json.loads((parent / "ablation_results.json").read_text())):
        raise ValueError("Historical raw-response rescoring differs from prior results")
    rows = prior.copy()
    references = {r["id"]: r for r in inputs["references"]}
    catalog = {c["key"]: c for c in inputs["command_set"]["commandSet"]}
    experiments = {(e["case_id"], e["variant"], e["arm"]): e for e in inputs["experiments"]}
    api_meta, checksums = {}, {}
    for provider in ("jev", "gpt"):
        directory = run / provider
        path = directory / "formal_receipts.jsonl"
        meta_path = directory / "formal_run.json"
        receipts = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
        metadata = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        api_meta[provider] = metadata
        expected_model = metadata.get("expected_model")
        if not partial:
            if metadata.get("status") != "complete" or len(receipts) != 250:
                raise ValueError(provider + ": incomplete formal run")
            probe = json.loads((directory / "probe_run.json").read_text())
            if probe["status"] != "complete" or probe["errors"] or len(probe["observed_models"]) != 1:
                raise ValueError("Missing successful single-version preflight")
            if expected_model != (GPT_MODEL if provider == "gpt" else probe["observed_models"][0]):
                raise ValueError("Formal model identity differs from preflight")
            if metadata["errors"] != sum(r["status"] != "ok" for r in receipts):
                raise ValueError("Error count mismatch")
            if metadata["automatic_retries"] != 0 or metadata["concurrency_per_provider"] != 1:
                raise ValueError("Unexpected retry or concurrency policy")
            if metadata["actual_observations"] != len(receipts):
                raise ValueError("Observation count mismatch")
            if metadata["actual_calls"] != sum(len(r["stages"]) for r in receipts):
                raise ValueError("Call count mismatch")
            if metadata["experiments_sha256"] != plan["experiments_sha256"]:
                raise ValueError("Metadata experiments mismatch")
            if metadata["plan_file_sha256"] != hashlib.sha256((run / "plan.json").read_bytes()).hexdigest():
                raise ValueError("Plan changed after runner started")
        seen = set()
        for receipt in receipts:
            identity = receipt["case_id"], receipt["variant"], receipt["arm"]
            if identity in seen or receipt["provider"] != provider:
                raise ValueError("Duplicate or wrong-provider observation")
            seen.add(identity)
            rows.append(decode_receipt(receipt, experiments[identity],
                                       references[receipt["case_id"]], catalog, expected_model))
        if path.exists():
            checksums[provider] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {
        "partial": partial, "observations": len(rows),
        "new_api_observations": sum(r["provider"] in {"jev", "gpt"} for r in rows),
        "new_api_calls": sum(r["http_calls"] for r in rows if r["provider"] in {"jev", "gpt"}),
        "models": {p: summarize_group([r for r in rows if r["provider"] == p]) for p in LABELS},
        "api_metadata": api_meta, "new_receipts_sha256": checksums,
    }
    for p in ("jev", "gpt"):
        meta = api_meta[p]
        print(p, meta.get("status", "not_started"), meta.get("actual_observations", 0),
              {a: (display_ratio(s["spec_original"]["exact_match"]),
                   display_ratio(s["extension_original"]["exact_match"]))
               for a, s in summary["models"][p].items()})
    if not partial:
        if len(rows) != 1250:
            raise ValueError("Expected 1250 observations across five providers")
        save(run / "five_model_results.json", rows)
        save(run / "five_model_summary.json", summary)
        save(run / "audit.json", {
            "observations": len(rows), "new_api_observations": summary["new_api_observations"],
            "new_api_calls": summary["new_api_calls"], "errors": sum(r["status"] != "ok" for r in rows),
            "prior_raw_rescoring_matches": True, "prior_evidence_unchanged": True,
            "frozen_task_and_transport_hashes_verified": True, "gpt_model_and_low_effort_verified": True,
            "all_candidate_ids_and_question_ids_validated": True,
            "second_stage_selected_only_by_model_gate": True, "no_output_repair": True,
            "source_sha256": plan["source_sha256"], "new_receipts_sha256": checksums,
        })
        report(run, summary, rows, references)
        save_examples(run, rows)
    return summary, rows


def report(run, summary, rows, references):
    models = summary["models"]
    jev_version = ", ".join(summary["api_metadata"]["jev"]["observed_models"])
    text = [
        "# 空调控制：Decider、Liquid、H2O、Jev、GPT 6.1 Sol low 对照", "",
        f"Jev 本轮返回版本：`{jev_version}`；GPT 使用 Bedrock `us.openai.gpt-6.1-sol`，"
        "每次请求显式设置 `reasoning.effort=low`。"
        "Jev/GPT各新增250条观察；三个GPU模型复用此前750条已核验观察，不重跑或改写旧证据。", "",
        "同一组五种方案：原始基线、仅改候选条件、仅改规则与问题、两项合并、"
        "先选Key再选Value的两阶段。原规范20题测原始与反转候选顺序，"
        "另10条新表达/反例只测原始顺序并单独统计。"
        "两阶段的两次请求都含完整30项能力集；第二步的Key只由模型第一步选择决定，仍可选omit。", "",
        "## 原规范20题：整条指令完全匹配", "",
        "| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p, model in models.items():
        text.append("| " + LABELS[p] + " | " + " | ".join(
            display_ratio(model[a]["spec_original"]["exact_match"]) for a in ARMS) + " |")
    text += [
        "", "表中为原始候选顺序的主结果。完整cmdKey/cmdValue集合必须与参考相同；"
        "任何多余、缺失、错值、调用或格式错误都计为失败。模型输出不补温标、不删多余指令。", "",
        "## 新表达与反例：另计10题", "",
        "此诊断集在较早三模型对照前已经冻结，沿用原答案；根据旧基线错误设计，"
        "不是独立盲测集，不与20题主结果混合为一个准确率。", "",
        "| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p, model in models.items():
        text.append("| " + LABELS[p] + " | " + " | ".join(
            display_ratio(model[a]["extension_original"]["exact_match"]) for a in ARMS) + " |")
    text += [
        "", "## 候选顺序与错误类型（原规范）", "",
        "| 模型 | 组别 | 原始顺序 | 反转顺序 | 输出改变 | 原始多余对 | 原始缺失对 | 调用/格式失败（两顺序） |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for p, model in models.items():
        for a, stats in model.items():
            o, r = stats["spec_original"], stats["spec_reversed"]
            text.append(f"| {LABELS[p]} | {ARM_LABELS[a]} | {display_ratio(o['exact_match'])} | "
                        f"{display_ratio(r['exact_match'])} | {stats['changed_cases']}/{stats['valid_order_pairs']} | "
                        f"{o['extra_command_rate']['numerator']} | {o['missing_command_rate']['numerator']} | "
                        f"{o['errors'] + r['errors']} |")
    text += [
        "", "两种顺序重复同20题，不是40个独立样本；API模型的换序差异还可能包含生成或服务波动。", "",
        "## 耗时与调用状态（原规范原始顺序）", "",
        "| 模型 | 组别 | 服务端均值 ms | 服务端P95 ms | 客户端均值 ms | 实际调用数 | 格式/调用失败 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for p, model in models.items():
        for a, stats in model.items():
            s = stats["spec_original"]
            server, client = s["server_ms"], s["client_ms"]
            mean = f"{server['mean']:.1f}" if server["count"] else "未提供"
            p95 = f"{server['p95']:.1f}" if server["count"] else "未提供"
            text.append(f"| {LABELS[p]} | {ARM_LABELS[a]} | {mean} | {p95} | "
                        f"{client.get('mean', 0):.1f} | {s['http_calls']} | {s['errors']} |")
    text += [
        "", "两阶段累加实际发生的两次调用。Jev为HTTPS服务，GPT为Bedrock Converse；"
        "GPU模型主要走本机loopback，旧Decider基线走HTTPS。"
        "各服务计时边界与处理方式不同，不能直接当作纯GPU或模型计算速度比较。"
        "Jev没有返回latency_ms时仅展示实测客户端耗时，不伪造服务端时间。", "",
        "## 传输与输出契约", "",
        "- 业务payload逐字节复用冻结模板，包括Query、完整30项Command Set、"
        "各问题说明、候选ID、描述和顺序。数值字段覆盖全部合法整数，不按答案筛选候选。",
        "- Jev直接调用原生 `/v1/systemone`，附加固定 `model=jev-latest`；"
        "正式响应版本必须与预检一致。既有应用转发层的16问/24候选限制不适用于原生调用，未修改应用服务。",
        "- GPT通过现有Bedrock模型配置调用；控制面确认该推理配置映射到GPT 6.1 Sol。"
        "Converse响应不回显模型ID，身份依据实际请求modelId与保存的ACTIVE推理配置。"
        "low参数保存在每次实际请求中。"
        "[OpenAI官方模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-sol)确认支持low。",
        "- GPT增加固定、无空调知识的JSON格式说明，要求回答每个Question ID并返回字符串Candidate ID。"
        "同时明确读取state内的任务规则。它一次生成全部答案，其他模型使用原生选择接口；"
        "业务输入一致，内部模板与推理机制并不相同。",
        "- GPT本轮未启用约束式JSON解码；严格核验完整题目集合和候选ID，"
        "只允许去除最外层JSON代码围栏。不修补缺失回答、不把数字转换成字符串、不纠正业务结果。"
        "maxTokens=8192为输出上限，effort始终low，不代表实际使用8192个token。",
        "- 每模型单客户端串行，Jev与GPT可同时运行于独立API。"
        "无自动重试、无答案补齐；预检独立保存，不进入正式成绩。",
        "",
        f"本轮新增API观察：{summary['new_api_observations']}；实际API调用：{summary['new_api_calls']}。"
        f"五模型共{summary['observations']}条观察，含复用的750条GPU历史观察。"
        "没有向真实空调下发控制。", "",
        "## 全部问题与实际回答（原始顺序）", "",
    ]
    lookup = {(r["provider"], r["case_id"], r["variant"], r["arm"]): r for r in rows}
    for case_id, reference in references.items():
        text += [f"### {case_id} {reference['title']}", "", "> " + reference["query"], "",
                 "参考：" + display_commands(reference["expected"]), "",
                 "| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |",
                 "|---|---|---|---|---|---|"]
        for p in LABELS:
            values = []
            for arm in ARMS:
                row = lookup[p, case_id, "original", arm]
                values.append(("✓ " if row["correct"] else "✗ ") + display_commands(row["cmdList"])
                              + (f"（{row['status']}）" if row["status"] != "ok" else ""))
            text.append("| " + LABELS[p] + " | " + " | ".join(values) + " |")
        text.append("")
    text += [
        "## 证据", "",
        "- [冻结计划](plan.json)、[全部任务模板](experiments.json)、[离线参考](references.json)、"
        "[指标](five_model_summary.json)、[逐条评分](five_model_results.json)、[核验记录](audit.json)。",
        "- [Jev原始调用](jev/formal_receipts.jsonl)、[GPT实际请求及完整SDK返回](gpt/formal_receipts.jsonl)。",
        "- [Bedrock模型配置](bedrock_profile.json)、[Jev运行记录](jev/formal_run.json)、"
        "[GPT运行记录](gpt/formal_run.json)。",
        "- [S03完整请求与回答](examples/S03.api_raw.json)、[N04反例完整请求与回答](examples/N04.api_raw.json)。",
        "- [此前三模型报告](../2026-10-30-prompt-ablation-v1/ABLATION.zh.md)。"
        "旧原始响应重新解码评分与已保存结果一致，文件哈希未改变。",
        "",
    ]
    (run / "FIVE_MODELS.zh.md").write_text("\n".join(text))


def save_examples(run, rows):
    output = run / "examples"
    output.mkdir(exist_ok=True)
    for case_id in ("S03", "N04"):
        records = []
        for provider in ("jev", "gpt"):
            for line in (run / provider / "formal_receipts.jsonl").read_text().splitlines():
                row = json.loads(line)
                if row["case_id"] == case_id and row["variant"] == "original":
                    records.append(row)
        save(output / (case_id + ".api_raw.json"), records)
        save(output / (case_id + ".all_model_outputs.json"),
             [r for r in rows if r["case_id"] == case_id and r["variant"] == "original"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    analyze(args.run, args.partial)
