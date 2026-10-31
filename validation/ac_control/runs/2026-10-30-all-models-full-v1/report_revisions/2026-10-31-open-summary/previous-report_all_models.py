"""Audit all nine complete runs and report every specification request layout."""

import argparse
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path

from all_models_protocol import PROVIDERS, ROOT, business_payload, digest, save, sha, stamp
from analyze import display_commands, display_ratio, grade, ratio, summarize, timing
from api_ablation_protocol import decode_gpt, decode_jev, gpt_request, jev_request
from run_candidate_benchmark import selected

NAMES = {
    "jev": "Jev", "gpt": "GPT 6.1 Sol · low", "decider": "Strands Decider v19",
    "liquid": "Liquid d1-2B", "pplx": "Perplexity Flash", "knowline": "KnowLine Gen5.5",
    "torchcast": "Torchcast", "clef": "Clef-Flash", "h2o": "H2O-Lightning",
}
PROJECT = Path(__file__).resolve().parents[2]


def receipt_bytes(folder):
    plain = folder / "receipts.jsonl"
    return plain.read_bytes() if plain.exists() else gzip.decompress((folder / "receipts.jsonl.gz").read_bytes())


def expected_choices(case, reference):
    result = dict.fromkeys(case["payload"]["questions"], "omit")
    result.update({c["cmdKey"]: c["cmdValue"] for c in reference["expected"]})
    return result


def decode(row, provider, expected_model):
    if provider == "gpt":
        assert row["response"]["ResponseMetadata"]["RetryAttempts"] == 0
        return decode_gpt(row["response"], row["payload"])
    assert row["response"] == json.loads(row["response_text"])
    if provider == "jev":
        return decode_jev(row["response"], row["payload"], expected_model)
    assert row["response"]["model"] == expected_model
    if provider == "h2o":
        assert row["response"]["attention_mode"] == "bidirectional"
    assert not row["response"].get("effort_used", {}).get("state_selection")
    return selected(row["response"], row["payload"])


def audit(root, providers=PROVIDERS, write=True):
    plan = json.loads((root / "plan.json").read_text())
    transfer = json.loads((root / "runtime-transfer.json").read_text())
    assert digest(root / "runtime-input.tar.gz") == transfer["sha256"]
    for name in ("candidate_server.py", "liquid_server.py"):
        assert digest(root / "runtime_sources" / name) == transfer["files"][name]
    for name, checksum in plan["input_sha256"].items():
        assert digest(root / name) == checksum, name
    for name, checksum in plan["source_sha256"].items():
        assert digest(root / "sources" / name) == checksum, name
        assert digest(Path(__file__).with_name(name)) == checksum, "Working inference helper changed: " + name
    assert digest(PROJECT / "docs/AC_Control_Test_Spec.md") == digest(root / "spec.md")
    cases = {(r["case_id"], r["order"]): r for r in json.loads((root / "cases.json").read_text())}
    refs = {r["id"]: r for r in json.loads((root / "references.json").read_text())}
    primary_refs = json.loads((root / "spec_references.json").read_text())
    jobs = json.loads((root / "schedule.json").read_text())
    command_names = {r["key"]: r["name"]
                     for r in json.loads((root / "command_set.json").read_text())["commandSet"]}
    planned = [(j, k) for j in jobs for k in j["keys"]]
    results, all_rows = {}, []
    for provider in providers:
        folder = root / "results" / provider
        meta = json.loads((folder / "run.json").read_text())
        assert meta["status"] in ("complete", "complete_with_errors"), provider
        assert meta["external_concurrency"] == 1 and meta["automatic_retries"] == 0
        assert meta["plan_sha256"] == digest(root / "plan.json")
        assert meta["runner_sha256"] == plan["source_sha256"]["run_all_models.py"]
        raw = receipt_bytes(folder)
        rows = [json.loads(line) for line in raw.splitlines()]
        assert len(rows) == len(planned) == meta["calls"] == 2049, provider
        assert meta["errors"] == sum(r["status"] != "ok" for r in rows)
        if provider == "gpt":
            profile = json.loads((folder / "bedrock_profile.json").read_text())
            assert profile["status"] == "ACTIVE" and profile["inferenceProfileId"] == plan["gpt_model"]
        elif provider != "jev":
            resumed = json.loads((root / "infrastructure/storage-initialization-controller-resume.json").read_text())
            initialized = json.loads((root / "logs/storage-initialization.json").read_text())
            assert resumed["read_only_initialization_complete"] and resumed["original_read_ahead_restored_kb"] == 128
            assert initialized["status"] == "complete" and initialized["read_bytes"] == initialized["total_bytes"]
            assert datetime.fromisoformat(meta["started_at"]) >= datetime.fromisoformat(resumed["recorded_at"])
            if provider == "knowline":
                amended = json.loads((root / "infrastructure/knowline-identity-amendment.json").read_text())
                failed = json.loads((root / "attempts/knowline-health-alias/attempt.json").read_text())
                assert amended["routing_and_health_identity_only"] and amended["business_inputs_unchanged"]
                assert amended["prior_decision_calls"] == failed["decision_calls"] == 0
                assert failed["warmup_calls"] == failed["formal_calls"] == 0
                assert not (root / "attempts/knowline-health-alias/results/knowline/receipts.jsonl").exists()
                launch_script = (root / "operations/start-knowline-nine-models-identity.sh").read_text()
                assert launch_script.count("--served-model-name " + meta["expected_model"]) == 2
                layout_proof = json.loads((root / "knowline-layout-analysis.json").read_text())
                assert layout_proof["model_inference_calls"] == 0 and layout_proof["checked_layouts"] == 620
                assert layout_proof["matched_actual_requests"] == 1860
                assert layout_proof["all_reconstructed_counts_match_recorded_usage"]
                assert layout_proof["cases_sha256"] == digest(root / "cases.json")
                assert layout_proof["receipts_sha256"] == hashlib.sha256(raw).hexdigest()
                assert layout_proof["analyzer_sha256"] == digest(Path(__file__).with_name("analyze_knowline_layout.py"))
        for sequence, (row, (job, key)) in enumerate(zip(rows, planned, strict=True)):
            assert row["sequence"] == sequence
            assert all(row[k] == job[k] for k in ("case_id", "dataset", "order", "language", "kind", "repetition"))
            assert row["field"] == key and row["provider"] == provider
            payload = business_payload(cases[job["case_id"], job["order"]], key)
            assert row["payload"] == payload
            assert sha(row["payload"]) == row["input_sha256"] == sha(payload)
            if provider == "gpt":
                transport = gpt_request(payload)
            elif provider == "jev":
                transport = jev_request(payload)
            else:
                transport = dict(payload, model=meta["expected_model"])
                if provider == "h2o":
                    transport["attention_mode"] = "bidirectional"
            assert row["transport_request"] == transport
            assert sha(row["transport_request"]) == row["transport_sha256"] == sha(transport)
            if provider == "gpt" and row.get("provider_error"):
                assert row["provider_error"]["ResponseMetadata"]["RetryAttempts"] == 0
            if row["status"] == "ok":
                assert row["http_status"] == 200
                choices = decode(row, provider, meta["expected_model"])
                assert choices == row["choices"]
                assert row["commands"] == [{"cmdKey": k, "cmdValue": v} for k, v in choices.items() if v != "omit"]
        scored = []
        for row in rows:
            if row["kind"] != "quality":
                continue
            ref = refs[row["case_id"]]
            scored.append({
                **{k: row[k] for k in ("case_id", "dataset", "language", "order", "status", "client_ms", "commands")},
                "server_ms": row.get("server_ms"),
                "category": ref["category"], "query": ref["query"], "expected": ref["expected"],
                "choices": row.get("choices", {}),
                "cmdList": [{"cmdName": command_names[c["cmdKey"]], **c} for c in row["commands"]],
                **grade(ref["expected"], row["commands"], row["status"]),
            })
        primary = [r for r in scored if r["dataset"] == "spec" and r["order"] == "original"]
        assert [r["case_id"] for r in primary] == [r["id"] for r in primary_refs]
        serial_rows = [r for r in rows if r["kind"] == "serial30"]
        full_rows = [r for r in rows if r["kind"] == "full30"]
        assert len(serial_rows) == 1800 and len(full_rows) == 60 and len(meta["blocks"]) == 60
        step_checks, layout_checks = [], []
        for ref in primary_refs:
            expected = expected_choices(cases[ref["id"], "original"], ref)
            for repetition in range(3):
                steps = [r for r in serial_rows if r["case_id"] == ref["id"] and r["repetition"] == repetition]
                complete = next(r for r in full_rows if r["case_id"] == ref["id"] and r["repetition"] == repetition)
                block = next(b for b in meta["blocks"] if b["case_id"] == ref["id"] and b["repetition"] == repetition)
                assert [r["field"] for r in steps] == list(expected) and block["calls"] == 30
                assert block["artifact_operations_inside_block"] == 0
                assert abs(block["http_sum_ms"] - sum(r["client_ms"] for r in steps)) < .01
                assert block["wall_ms"] >= block["http_sum_ms"]
                assert block["started_at"] <= steps[0]["started_at"] <= steps[-1]["finished_at"] <= block["finished_at"]
                combined = {k: v for r in steps for k, v in r.get("choices", {}).items()}
                serial_commands = [{"cmdKey": k, "cmdValue": v} for k, v in combined.items() if v != "omit"]
                serial_status = "ok" if all(r["status"] == "ok" for r in steps) else "error"
                for row in steps:
                    key = row["field"]
                    step_checks.append({
                        "case_id": ref["id"], "category": ref["category"], "repetition": repetition,
                        "key": key, "expected": expected[key], "actual": row.get("choices", {}).get(key),
                        "correct": row["status"] == "ok" and row.get("choices", {}).get(key) == expected[key],
                        "status": row["status"], "client_ms": row["client_ms"],
                    })
                layout_checks.append({
                    "case_id": ref["id"], "category": ref["category"], "repetition": repetition,
                    "serial_correct": grade(ref["expected"], serial_commands, serial_status)["correct"],
                    "full_correct": grade(ref["expected"], complete["commands"], complete["status"])["correct"],
                    "serial_commands": serial_commands, "full_commands": complete["commands"],
                    "serial_status": serial_status, "full_status": complete["status"],
                    "serial_choices": combined, "full_choices": complete.get("choices", {}),
                    "serial_wall_ms": block["wall_ms"], "serial_http_sum_ms": block["http_sum_ms"],
                    "full_ms": complete["client_ms"],
                    "full_field_hits": sum(complete["status"] == "ok" and complete.get("choices", {}).get(k) == v
                                           for k, v in expected.items()),
                    "full_active_hits": sum(complete["status"] == "ok" and complete.get("choices", {}).get(k) == v
                                            for k, v in expected.items() if v != "omit"),
                    "full_omit_hits": sum(complete["status"] == "ok" and complete.get("choices", {}).get(k) == v
                                          for k, v in expected.items() if v == "omit"),
                    "changed_fields": ([k for k in expected if combined.get(k) != complete.get("choices", {}).get(k)]
                                       if serial_status == "ok" and complete["status"] == "ok" else None),
                })

        def layout_metrics(checks, steps):
            active = [r for r in steps if r["expected"] != "omit"]
            omitted = [r for r in steps if r["expected"] == "omit"]
            comparable = [r for r in checks if r["changed_fields"] is not None]
            successful_steps = [r for r in steps if r["status"] == "ok"]
            return {
                "single_step_fields": ratio(sum(r["correct"] for r in steps), len(steps)),
                "single_active_fields": ratio(sum(r["correct"] for r in active), len(active)),
                "single_omit_fields": ratio(sum(r["correct"] for r in omitted), len(omitted)),
                "serial_tasks": ratio(sum(r["serial_correct"] for r in checks), len(checks)),
                "full_tasks": ratio(sum(r["full_correct"] for r in checks), len(checks)),
                "full_fields": ratio(sum(r["full_field_hits"] for r in checks), len(checks) * 30),
                "full_active_fields": ratio(sum(r["full_active_hits"] for r in checks), len(active)),
                "full_omit_fields": ratio(sum(r["full_omit_hits"] for r in checks), len(omitted)),
                "single_step_errors": len(steps) - len(successful_steps),
                "single_successful_fields": ratio(sum(r["correct"] for r in successful_steps), len(successful_steps)),
                "serial_tasks_with_errors": sum(r["serial_status"] != "ok" for r in checks),
                "full_tasks_with_errors": sum(r["full_status"] != "ok" for r in checks),
                "single_step_ms": timing(r["client_ms"] for r in steps),
                "serial_wall_ms": timing(r["serial_wall_ms"] for r in checks),
                "full_ms": timing(r["full_ms"] for r in checks),
                "changed_layout_tasks": sum(bool(r["changed_fields"]) for r in comparable),
                "comparable_layout_tasks": len(comparable),
            }

        repeat_stability = {}
        for mode in ("serial", "full"):
            eligible, changed = [], []
            for ref in primary_refs:
                repeated = [r for r in layout_checks if r["case_id"] == ref["id"]]
                assert len(repeated) == 3
                if any(r[mode + "_status"] != "ok" for r in repeated):
                    continue
                eligible.append(ref["id"])
                if len({tuple(sorted(r[mode + "_choices"].items())) for r in repeated}) > 1:
                    changed.append(ref["id"])
            repeat_stability[mode] = {"comparable_cases": eligible, "changed_cases": changed}

        results[provider] = {
            "model": meta["model"], "expected_model": meta["expected_model"],
            "calls": len(rows), "errors": meta["errors"], "hostname": meta["hostname"],
            "run_timing": {
                "wall_seconds": (datetime.fromisoformat(meta["finished_at"])
                                 - datetime.fromisoformat(meta["started_at"])).total_seconds(),
                "all_request_seconds": sum(r["client_ms"] for r in rows) / 1000,
            },
            "error_rows": [
                {k: r.get(k) for k in ("sequence", "case_id", "kind", "repetition", "field",
                                       "status", "error_type", "error", "provider_error")}
                for r in rows if r["status"] != "ok"
            ],
            "primary": summarize(primary), "primary_rows": primary,
            "quality": {dataset: {order: summarize([
                r for r in scored if r["dataset"] == dataset and r["order"] == order])
                for order in ("original", "reversed")}
                for dataset in ("spec", "extension", "validation", "chinese")},
            "quality_rows": scored,
            "hosted_observability": {
                label: {
                    "requests": len(subset),
                    "server_ms": timing(r["server_ms"] for r in subset if r.get("server_ms") is not None),
                    "cache_fields_observed": any(
                        "cacheReadInputTokens" in r.get("response", {}).get("usage", {}) for r in subset),
                    "reported_cache_read_requests": sum(
                        r.get("response", {}).get("usage", {}).get("cacheReadInputTokens", 0) > 0 for r in subset),
                    "reported_cache_write_requests": sum(
                        r.get("response", {}).get("usage", {}).get("cacheWriteInputTokens", 0) > 0 for r in subset),
                }
                for label, subset in {
                    "primary": [r for r in rows if r["kind"] == "quality"
                                and r["dataset"] == "spec" and r["order"] == "original"],
                    "single_step": serial_rows, "full30": full_rows,
                }.items()
            } if provider in ("jev", "gpt") else None,
            "layouts": layout_metrics(layout_checks, step_checks),
            "layouts_by_category": {category: layout_metrics(
                [r for r in layout_checks if r["category"] == category],
                [r for r in step_checks if r["category"] == category])
                for category in ("single", "multi")},
            "layouts_by_case": {ref["id"]: layout_metrics(
                [r for r in layout_checks if r["case_id"] == ref["id"]],
                [r for r in step_checks if r["case_id"] == ref["id"]]) for ref in primary_refs},
            "layout_checks": layout_checks, "single_step_checks": step_checks,
            "repeat_stability": repeat_stability,
            "single_error_breakdown": {
                "missed_actions": sum(r["status"] == "ok" and r["expected"] != "omit" and r["actual"] == "omit"
                                      for r in step_checks),
                "wrong_action_values": sum(r["status"] == "ok" and r["expected"] != "omit"
                                          and r["actual"] not in ("omit", r["expected"]) for r in step_checks),
                "extra_actions": sum(r["status"] == "ok" and r["expected"] == "omit" and r["actual"] != "omit"
                                     for r in step_checks),
                "interface_errors": sum(r["status"] != "ok" for r in step_checks),
            },
            "evidence": {"receipts_sha256": hashlib.sha256(raw).hexdigest(),
                         "run_sha256": digest(folder / "run.json"),
                         "started_at": meta["started_at"], "finished_at": meta["finished_at"]},
        }
        assert sum(results[provider]["single_error_breakdown"].values()) == sum(
            not r["correct"] for r in step_checks)
        examples = root / "examples"
        for case_id in ("S01", "S03", "S04", "M07", "M08", "M09"):
            case_rows = [r for r in rows if r["case_id"] == case_id and r["order"] == "original"
                         and r["kind"] in ("serial30", "full30") and r["repetition"] == 0]
            save(examples / f"{provider}-{case_id}.json",
                 {"expected_offline_only": refs[case_id]["expected"], "raw_receipts": case_rows})
        all_rows.extend(rows)
    local_hosts = {m["hostname"] for p, m in results.items() if p not in ("jev", "gpt")}
    assert len(local_hosts) <= 1, "Local models must use the same dedicated host"
    all_rows.sort(key=lambda r: r["started_at"])
    for left, right in zip(all_rows[:-1], all_rows[1:], strict=True):
        assert datetime.fromisoformat(left["finished_at"]) <= datetime.fromisoformat(right["started_at"])
    result = {
        "generated_at": stamp(), "passed": True, "providers": list(providers),
        "observed_calls": len(all_rows), "formal_calls": len(providers) * 2016,
        "warmups": len(providers) * 33,
        "errors": sum(m["errors"] for m in results.values()), "overlap_count": 0,
        "local_hostnames": sorted(local_hosts),
        "same_ordered_business_requests": True, "all_results_new_live_calls": True,
        "output_repair": False, "references_sent": False,
        "analyzer_sha256": digest(Path(__file__)), "models": results,
        "grading_sources_sha256": {
            name: digest(Path(__file__).with_name(name))
            for name in ("report_all_models.py", "analyze.py", "prepare.py", "analyze_knowline_layout.py")},
    }
    if write:
        assert tuple(providers) == PROVIDERS, "Published reports require all nine complete runs"
        save(root / "summary.json", result)
        save(root / "audit.json", {k: v for k, v in result.items() if k != "models"} | {
            "evidence": {p: m["evidence"] for p, m in results.items()}})
        for name in result["grading_sources_sha256"]:
            target = root / "analysis_sources" / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(Path(__file__).with_name(name).read_bytes())
    return result


def render(root, result):
    assert tuple(result["providers"]) == PROVIDERS
    models = result["models"]
    link = "../validation/ac_control/runs/" + root.name
    local = PROVIDERS[2:]

    def best(providers, mode):
        highest = max(models[p]["layouts"][mode + "_tasks"]["numerator"] for p in providers)
        candidates = [p for p in providers if models[p]["layouts"][mode + "_tasks"]["numerator"] == highest]
        metric = "serial_wall_ms" if mode == "serial" else "full_ms"
        return min(candidates, key=lambda p: models[p]["layouts"][metric]["mean"])

    def outcome(provider, mode):
        metrics = models[provider]["layouts"]
        duration = metrics["serial_wall_ms" if mode == "serial" else "full_ms"]["mean"] / 1000
        return f"{NAMES[provider]}：{display_ratio(metrics[mode + '_tasks'])}，平均 {duration:.3f} 秒"

    fastest = min(PROVIDERS, key=lambda p: models[p]["layouts"]["full_ms"]["mean"])
    text = [
        "# 空调控制九模型完整统一测试", "",
        f"测试日期：{models['jev']['evidence']['started_at'][:10]}（UTC）。"
        "按 [AC_Control_Test_Spec.md](AC_Control_Test_Spec.md) 的原文、完整 30 项能力与标准答案，"
        "重新实测 Strands Decider、Liquid、H2O、Perplexity、KnowLine、Torchcast、Clef、Jev 与 GPT。"
        "本轮所有九模型均产生新的原始调用记录，旧七模型和五模型成绩分别保留为历史参考。", "",
        "本次补齐了两项覆盖：**Strands 与 Liquid 加入统一测试；单步决策、30 步串行、"
        "一次全答都覆盖规范全部 20 题，每题重复三轮。** 单步与串行使用同一批实际请求，"
        "单步按字段评分，串行和全答按完整命令集合评分。", "",
        "以下结论仅针对本轮固定规范与部署。前三项按整组正确次数优先、同分时按平均耗时选择：", "",
        "- 一次全答：" + outcome(best(PROVIDERS, "full"), "full") + "。",
        "- 本地模型一次全答：" + outcome(best(local, "full"), "full") + "。",
        "- 本地模型 30 步串行：" + outcome(best(local, "serial"), "serial") + "。",
        "- 全答平均响应最快：" + outcome(fastest, "full") + "。", "",
        "60 组来自 20 条指令各重复三轮，仍需结合下方新表达与中文附项判断适用范围。", "",
        "## 过程与统一口径", "",
        "| 项目 | 每模型实际覆盖 |",
        "|---|---|",
        "| 规范主成绩 | 原序 20 条完整请求各一次：单指令 10、多指令 10，共 40 个预期命令对 |",
        "| 质量附项 | 同 20 题反序；10 条英文诊断、24 条英文新题、24 条中文翻译，各含原序与反序 |",
        "| 单步决策 | 20 Query × 30 Key × 3 轮，共 1,800 次实际单字段请求 |",
        "| 30 步串行 | 上述请求每 30 步组成一个完整任务，共 60 个任务 |",
        "| 一次全答 | 相同 20 Query × 3 轮，每请求回答完整 30 字段，共 60 个任务 |",
        "| 预热 | 3 次 S03 全答；质量请求之后，对 S03 的 30 种字段形状各预热一次 |",
        "| 合计 | 2,049 次：2,016 正式、33 预热；九模型共 18,441 次 |", "",
        "冻结业务输入、选项及调用顺序后才开始推理。按 Jev→GPT→Strands→Liquid→Perplexity→KnowLine→"
        "Torchcast→Clef→H2O 依次运行，所有外部请求串行；每个模型的 156 次质量请求和布局顺序相同。"
        "按题号与轮次交替串行/全答的先后次序，保留服务原生缓存。"
        "逐字段时每次保留完整状态、能力表和该字段的全部选项，不把上一字段的回答传入下一字段。", "",
        "30 步总时间由实际整轮墙钟测量，计时结束后才写盘或上传证据。"
        "字段调用时间使用每次客户端往返，完整请求时间同样包含服务及网络开销。"
        "七个本地模型使用独占 g6.xlarge/L4 原生服务，Jev/GPT 使用托管 API；"
        "统一任务与流程不等于统一托管硬件。所有原始选择保留，只移除 omit、补展示用 cmdName，"
        "不补单位、不删除额外命令，不向真实设备执行控制。", "",
        "整个测试脚本还要执行质量附项、预热和证据上传，运行时长远大于一条业务指令的延迟。"
        "逐模型的脚本墙钟时间与全部请求计时之和另存于 `summary.json` 的 `run_timing`，"
        "不用于替代下方三种请求方式的响应时间。", "",
        "GPT 固定 `us.openai.gpt-6.1-sol`、每请求显式 low effort、8192 输出 token 上限；"
        "系统提示只约束读取输入和 JSON 输出格式。Jev 以首个成功预热的返回版本锁定整轮。", "",
        "### 模型与运行条件", "",
        "| 模型 | 固定版本 | 原生推理路径 |",
        "|---|---|---|",
    ]
    runtimes = {
        "jev": "托管原生 SystemOne API",
        "gpt": "Bedrock Converse，low effort",
        "decider": "vLLM 0.31.0，v19；同常驻镜像，max-num-seqs=1、max-inflight-questions=1、GPU utilization=0.26",
        "liquid": "官方 Transformers system_one，BF16",
        "pplx": "官方 fast 路径，BF16、编译与 CUDA graphs",
        "knowline": "官方 SGLang 前后端，FP8；read-twice 按整请求 ≤3000 token 启用；16 个评分线程、mem-fraction-static=0.72",
        "torchcast": "官方非因果 BF16；原生候选分组及 CUDA graphs",
        "clef": "官方联合 schema head，BF16",
        "h2o": "官方 vLLM 双向注意力，FP8、eager、max-num-seqs=1、GPU utilization=0.34",
    }
    for provider, model in models.items():
        version = model["model"].get("revision", model["expected_model"])
        if provider == "decider":
            version = "v19；upstream 63d24ae286e50105fba0bd1db15b0e243aea4650"
        text.append(f"| {NAMES[provider]} | `{version}` | {runtimes[provider]} |")
    text += [
        "", "原测试机及美国其他可用区申请均遇到容量不足，遂从已停止的测试机制作临时镜像，"
        "使用东京区域预留容量启动同规格 g6.xlarge：4 vCPU、16 GiB 内存、单张 NVIDIA L4。"
        "原有五个候选环境及模型文件随磁盘复制，"
        "Strands 与 Liquid 使用固定制品；推理前重新核验模型 SHA-256 和 H2O 官方补丁。"
        "根盘由 200 GiB 扩为 250 GiB 以容纳新增镜像和权重，七个本地模型随后在同一台 L4 上依次独占运行。"
        "新盘先完成并行只读预加载和模型文件校验，磁盘预读恢复原来的 128 KiB 后才允许启动推理；"
        "预加载与正式模型调用没有重叠。"
        "原常驻服务没有改动。容量恢复与模型装载时间不计入请求延迟。"
        "原生引擎的精度、显存预算和内部批处理参数分别保留；结果比较这些固定部署方案，"
        "不能视为每个模型在 L4 上调优后的性能上限。"
        "七个本地模型的计时均在测试机内通过 loopback 完成；东京区域不会给它们增加"
        "跨区域请求往返。Jev/GPT 保留原美国调用客户端，二者托管硬件及网络开销仍不同。"
        f"详细变更见[实际基础设施修订]({link}/infrastructure/actual-region-amendment.json)。", "",
        "KnowLine 首次健康检查返回官方默认别名 `m`，与统一测试要求的仓库身份不一致，"
        "在发送任何测试题前中止。随后仅把前后端服务名统一为固定仓库名，"
        "模型权重、代码、推理参数和业务请求均未改动，再从完整预热开始。"
        f"[这次零测试调用的启动记录]({link}/attempts/knowline-health-alias/)和"
        f"[身份配置修订]({link}/infrastructure/knowline-identity-amendment.json)单独保留；"
        "没有丢弃或重跑已得到的题目回答。", "",
        "完整能力映射保存在每次请求的 state；范围值展开为全部整数候选，再加 omit。"
        "自动除霜的状态值 2–4 仍在能力表中，但按规范不得作为用户控制选项。"
        "本批规范没有小数温度或真实设备初始状态，不报告小数处理能力或设备最终状态。", "",
        "## 规范 20 题主结果", "",
        "每条原序 Query 一次完整 30 字段请求；多发、漏发或错值均判整题失败。"
        "本表时间含错误回答，不混入扩展题、换序、预热或布局重复。", "",
        "| 模型 | 单指令 | 多指令 | 严格全对 | 完整请求均值 | P50 | P95 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider, model in models.items():
        main = model["primary"]
        text.append(f"| {NAMES[provider]} | " + " | ".join(display_ratio(main[k]) for k in (
            "single_exact", "multi_exact", "exact_match")) + " | "
            + " | ".join(f"{main['client_ms'][k]/1000:.3f} 秒" for k in ("mean", "p50", "p95")) + " |")
    text += [
        "", "| 模型 | Key 精确率 | Key 召回率 | 已选对 Key 的 Value 准确率 | 多余命令比例 | 缺失命令比例 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for provider, model in models.items():
        text.append(f"| {NAMES[provider]} | " + " | ".join(display_ratio(model["primary"][k]) for k in (
            "key_precision", "key_recall", "value_accuracy_given_correct_key",
            "extra_command_rate", "missing_command_rate")) + " |")
    text += [
        "", "Value 准确率以选对 Key 为条件，不能代替完整命令正确率。"
        "多余和缺失按 Key/Value 命令对计算：同一 Key 选错 Value，会同时产生一个非参考命令对"
        "和一个缺失的参考命令对，并非重复统计两条实际下发动作。"
        "标准答案仅用于离线评分；换序和扩展题不计入上表主成绩。", "",
        '<a id="request-layouts"></a>', "",
        "## 全部 20 题：三种请求方式的时间与准确率", "",
        "| 模型 | 单步均值 | 单步字段正确 | 30 步串行均值 | 串行整组正确 | 一次全答均值 | 全答整组正确 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider, model in models.items():
        m = model["layouts"]
        text.append(f"| {NAMES[provider]} | {m['single_step_ms']['mean']:.1f} ms"
                    f" | {display_ratio(m['single_step_fields'])} | {m['serial_wall_ms']['mean']/1000:.3f} 秒"
                    f" | {display_ratio(m['serial_tasks'])} | {m['full_ms']['mean']/1000:.3f} 秒"
                    f" | {display_ratio(m['full_tasks'])} |")
    text += [
        "", "本表完整覆盖规范的 20 种业务指令；60 个完整任务是每题三轮重复，"
        "不是 60 道独立新题。1,800 个字段选择中应执行 120 次、应 omit 1,680 次。"
        "全部选 omit 也会得到 93.3% 的字段正确率，但 60 个控制任务都会失败。"
        "一个多余动作即可使整组失败，字段正确率不宜单独作为任务准确率。", "",
        "| 模型 | 应执行字段正确 | 应 omit 字段正确 | 全答字段正确 | 串行 P95 | 全答 P95 | 双方成功时选择改变的任务 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider, model in models.items():
        m = model["layouts"]
        text.append(f"| {NAMES[provider]} | {display_ratio(m['single_active_fields'])}"
                    f" | {display_ratio(m['single_omit_fields'])} | {display_ratio(m['full_fields'])}"
                    f" | {m['serial_wall_ms']['p95']/1000:.3f} 秒 | {m['full_ms']['p95']/1000:.3f} 秒"
                    f" | {m['changed_layout_tasks']}/{m['comparable_layout_tasks']} |")
    gpt_step = models["gpt"]["hosted_observability"]["single_step"]
    gpt_full = models["gpt"]["hosted_observability"]["full30"]
    text += [
        "", "全答的执行字段与 omit 分项也保存在逐条评分 JSON。"
        "“选择改变”仅在同一题同一轮两种布局都成功返回时比较，接口失败不算模型改变了选择；"
        "重复三轮可以观察稳定性，但没有单独控制数值计算、缓存及生成随机性，不能据此断定单一原因。", "",
        f"GPT 有服务端计时的 {gpt_step['server_ms']['count']:,} 次单字段响应，"
        f"Bedrock 服务端延迟均值为 {gpt_step['server_ms']['mean']:.1f} ms；"
        f"{gpt_full['server_ms']['count']} 次全答为 {gpt_full['server_ms']['mean']/1000:.3f} 秒。"
        "该指标仍包含服务端调度等成本，"
        "不能进一步分离为纯模型计算。"
        f"单字段有 {gpt_step['reported_cache_read_requests']}/1,800 次、"
        f"全答有 {gpt_full['reported_cache_read_requests']}/60 次报告缓存读取。"
        "未主动配置缓存，保留实际 usage；Jev 没有返回可比的服务端耗时与缓存字段，"
        "不能仅由其速度推断内部模型规模或实现。", "",
        "### 单指令与多指令分别比较", "",
        "| 模型 | 类型 | 单步均值 / 字段正确 | 串行均值 / 整组正确 | 全答均值 / 整组正确 |",
        "|---|---|---:|---:|---:|",
    ]
    for provider, model in models.items():
        for category, label in (("single", "单指令"), ("multi", "多指令")):
            m = model["layouts_by_category"][category]
            text.append(f"| {NAMES[provider]} | {label} | {m['single_step_ms']['mean']:.1f} ms · "
                        f"{display_ratio(m['single_step_fields'])} | {m['serial_wall_ms']['mean']/1000:.3f} 秒 · "
                        f"{display_ratio(m['serial_tasks'])} | {m['full_ms']['mean']/1000:.3f} 秒 · "
                        f"{display_ratio(m['full_tasks'])} |")
    text += [
        "", "## 各题的完整请求与选择", "",
        "下表为规范主成绩的逐题判断；每题按实际命令与规范参考比较，额外动作全部保留。", "",
        "| 用例 | Query | 标准命令 | " + " | ".join(NAMES.values()) + " |",
        "|---|---|---|" + "---|" * 9,
    ]
    refs = json.loads((root / "spec_references.json").read_text())
    for index, ref in enumerate(refs):
        cells = []
        for model in models.values():
            row = model["primary_rows"][index]
            if row["status"] != "ok":
                cells.append("请求失败：" + row["status"])
                continue
            cells.append("正确" if row["correct"] else "；".join(
                label + ", ".join(f"{k}={v}" for k, v in row[field])
                for field, label in (("extra", "多发 "), ("missing", "漏发 ")) if row[field]) or row["status"])
        text.append(f"| {ref['id']} | {ref['query']} | {display_commands(ref['expected'])} | "
                    + " | ".join(cells) + " |")
    text += [
        "", f"[冻结问题与全部选项]({link}/cases.json) · [完整能力集]({link}/command_set.json) · "
        f"[真实请求与回答示例]({link}/examples/) · [全部原始记录]({link}/results/)。"
        "示例保存 S01、S03、S04、M07、M08、M09 第一轮的完整串行与全答原始响应。", "",
        "### 一个具体例子：只要求开机", "",
        "S01 原文为 `Turn on the air conditioner.`，完整请求仍包含全部 30 个字段。"
        "`t_power` 的候选为 `0`（关机）、`1`（开机）、`omit`（不下发该字段）；"
        "正确选择是 `t_power=1`，其余 29 个字段均为 `omit`。"
        "下表直接列出规范主请求中各模型实际选择的全部非 omit 字段。", "",
        "| 模型 | 实际命令 | 完整任务判断 |", "|---|---|---|",
    ]
    for provider, model in models.items():
        row = next(r for r in model["primary_rows"] if r["case_id"] == "S01")
        text.append(f"| {NAMES[provider]} | {display_commands(row['commands']) or '无命令'}"
                    f" | {'正确' if row['correct'] else '失败'} |")
    text += [
        "", "Strands 在本例全部选择 omit，因此没有开机；Liquid 选对开机，"
        "同时额外设置摆风角度、跟随、8°C 制热和室外自清洁，因此也判失败。"
        "多发 `0` 仍是修改设备设置，不能视为“没有动作”。完整选项和原始响应可从上方证据链接核对。", "",
        "### 每题三轮的整组正确率与时间", "",
        "每格依次为“串行答对轮数 / 全答答对轮数；串行均值 / 全答均值（秒）”。", "",
        "| 用例 | " + " | ".join(NAMES.values()) + " |",
        "|---|" + "---|" * 9,
    ]
    for ref in refs:
        cells = []
        for model in models.values():
            m = model["layouts_by_case"][ref["id"]]
            cells.append(f"{m['serial_tasks']['numerator']}/3 · {m['full_tasks']['numerator']}/3；"
                         f"{m['serial_wall_ms']['mean']/1000:.3f} / {m['full_ms']['mean']/1000:.3f}")
        text.append(f"| {ref['id']} | " + " | ".join(cells) + " |")
    text += [
        "", "### 同一种请求方式在三轮中是否改变选择", "",
        "仅比较三轮都返回有效选择的用例；此处检查全部 30 个字段的选择是否相同，"
        "不只是比较三轮是否都答对。接口失败导致无法完整比较的用例从本项排除，"
        "但仍保留在前述准确率分母中。", "",
        "| 模型 | 串行：选择有变化 / 可比较用例 | 全答：选择有变化 / 可比较用例 |",
        "|---|---:|---:|",
    ]
    for provider, model in models.items():
        cells = []
        for mode in ("serial", "full"):
            stable = model["repeat_stability"][mode]
            cells.append(f"{len(stable['changed_cases'])}/{len(stable['comparable_cases'])}")
        text.append(f"| {NAMES[provider]} | " + " | ".join(cells) + " |")
    text += [
        "", "## 换序与中英文扩展附项", "",
        "同一原题反转选项、英文新题及其中文翻译分别统计。中文只翻译用户 Query，"
        "能力表与规则保留英文；这些是既有冻结题，不能称为新的独立盲测。"
        "Clef 官方实现会按选项 ID 排序，接口字典反序不能检验其模型对实际候选位置的敏感度。", "",
        "| 模型 | 规范反序 | 英文诊断：原 / 反 | 英文新题：原 / 反 | 中文翻译：原 / 反 |",
        "|---|---:|---:|---:|---:|",
    ]
    for provider, model in models.items():
        cells = [display_ratio(model["quality"]["spec"]["reversed"]["exact_match"])]
        for dataset in ("extension", "validation", "chinese"):
            cells.append(" · ".join(display_ratio(model["quality"][dataset][o]["exact_match"])
                                    for o in ("original", "reversed")))
        text.append(f"| {NAMES[provider]} | " + " | ".join(cells) + " |")
    text += [
        "", "## 接口异常与选择错误分别解释", "",
        "所有尝试均留在分母，失败请求不重试、不默认补 omit。"
        "前述端到端整组成绩仍包括这些失败；成功响应的字段正确率用来区分模型选错与没有拿到答案。", "",
        "| 模型 | 单步请求异常 | 成功单步响应中字段正确 | 含异常的串行任务 | 含异常的全答任务 |",
        "|---|---:|---:|---:|---:|",
    ]
    for provider, model in models.items():
        m = model["layouts"]
        text.append(f"| {NAMES[provider]} | {m['single_step_errors']}/1,800"
                    f" | {display_ratio(m['single_successful_fields'])}"
                    f" | {m['serial_tasks_with_errors']}/60 | {m['full_tasks_with_errors']}/60 |")
    text += [
        "", "下表将 1,800 次单字段调用中的失败分为互斥的四类，四项之和等于字段错误总数。"
        "其中“漏动作”是模型成功返回 omit，“接口失败”是没有得到有效选择，二者分别计数。", "",
        "| 模型 | 漏掉应执行字段 | 选错执行值 | 多发未请求字段 | 接口或格式失败 |",
        "|---|---:|---:|---:|---:|",
    ]
    for provider, model in models.items():
        text.append(f"| {NAMES[provider]} | " + " | ".join(
            str(model["single_error_breakdown"][key])
            for key in ("missed_actions", "wrong_action_values", "extra_actions", "interface_errors")) + " |")
    error_rows = [(provider, row) for provider, model in models.items() for row in model["error_rows"]]
    if error_rows:
        text += ["", "| 模型 | 用例 / 轮次 | 请求方式 / 字段 | 异常 |", "|---|---|---|---|"]
        for provider, row in error_rows:
            reason = row["error_type"] or row["error"] or row["status"]
            text.append(f"| {NAMES[provider]} | {row['case_id']} / {row['repetition']+1}"
                        f" | {row['kind']} / {row['field'] or '全部'} | {reason} |")
        text += [
            "", "GPT 的三次 `ServiceUnavailableException` 发生在第三轮串行的 S06（两个字段）"
            "和 M07（一个字段），影响两组任务；相应字段没有答案，不能称为模型选错了三个值。"
            "规范主成绩和 60 次全答没有这些接口异常。", "",
        ]
    text += [
        "## 机制、结论与对照边界", "",
        "一个完整请求的内部计算方式因服务而异：Strands 与 H2O 分字段创建评分任务；"
        "Liquid、Perplexity 和 Clef 有原生多问题处理路径；KnowLine 每题前向，完整请求先预热共享前缀，"
        "再通过 16 个线程提交评分，且按整请求长度决定是否重复输入；"
        "Torchcast 大候选集合采用分组选择，完整多字段可能走不同图执行路径。"
        "GPT 一次生成全部字段的 JSON；Jev 内部硬件、算法及缓存明细未由调用记录揭示。"
        "具体机制见[此前模型差异说明](AC_SPEC_UNIFIED_RESULTS.md#model-differences)"
        "和[固定版本候选资料](AC_MODEL_CANDIDATES.md)。这些资料解释实现差异，"
        "本轮时间与准确率以上方新实测为准。", "",
    ]
    decider = models["decider"]
    liquid = models["liquid"]
    pplx = models["pplx"]["layouts"]
    knowline = models["knowline"]
    torchcast = models["torchcast"]["layouts"]
    clef = models["clef"]
    h2o = models["h2o"]
    liquid_passes = "、".join(
        case_id for case_id, metrics in liquid["layouts_by_case"].items()
        if metrics["serial_tasks"]["numerator"])
    text += [
        f"**Strands 的主要问题是漏动作。** 1,800 次单字段请求中，有 "
        f"{decider['single_error_breakdown']['missed_actions']} 次将应执行字段选为 omit，"
        f"另有 {decider['single_error_breakdown']['extra_actions']} 次多发。"
        f"串行整组为 {display_ratio(decider['layouts']['serial_tasks'])}，"
        f"全答为 {display_ratio(decider['layouts']['full_tasks'])}；"
        f"{decider['layouts']['comparable_layout_tasks']} 组可比较任务中有 "
        f"{decider['layouts']['changed_layout_tasks']} 组选择发生变化。"
        "当前基线的语义错误没有通过拆分问题得到解决。", "",
        "**Liquid 的主要问题是多发动作。** 单字段模式选对了全部必要动作，但额外下发 "
        f"{liquid['single_error_breakdown']['extra_actions']} 个未请求字段；"
        f"串行仅 {liquid_passes} 存在完整答对的轮次，合计 "
        f"{display_ratio(liquid['layouts']['serial_tasks'])}。"
        f"全答为 {display_ratio(liquid['layouts']['full_tasks'])}。"
        "串行与全答的字段错误分布不同，不能把拆分本身当作可靠的准确率优化。", "",
        "**Perplexity 对请求方式尤其敏感。** "
        f"串行整组为 {display_ratio(pplx['serial_tasks'])}，"
        f"全答为 {display_ratio(pplx['full_tasks'])}；"
        f"串行平均 {pplx['serial_wall_ms']['mean']/1000:.3f} 秒，"
        f"全答 {pplx['full_ms']['mean']/1000:.3f} 秒。"
        "本轮支持继续验证其逐字段方案，但不能据此采用其全答方案。"
        "扩展题本轮只测了全答，尚不能将规范题上的串行表现推广到所有新表达。"
        "这些结果证明当前部署受请求布局影响，未单独隔离提示上下文、内部批处理和数值路径，"
        "因此不能把全部差异归因于其中一个因素。", "",
        "**KnowLine 的串行方式也提高了本轮规范正确率，但需要更长时间。** "
        f"串行为 {display_ratio(knowline['layouts']['serial_tasks'])}、"
        f"{knowline['layouts']['serial_wall_ms']['mean']/1000:.3f} 秒；"
        f"全答为 {display_ratio(knowline['layouts']['full_tasks'])}、"
        f"{knowline['layouts']['full_ms']['mean']/1000:.3f} 秒。"
        "串行修复 S04 多发摄氏温度的错误，M08 多发摆风角度的错误仍存在。"
        f"本轮 S03 单步均值也为 {knowline['layouts_by_case']['S03']['single_step_ms']['mean']:.1f} ms，"
        "高于旧七模型仅重复 S03 时的 100.8 ms；因此差异不只是汇总了更多题目。"
        "两轮的请求历史、缓存状态与测试实例不同，本轮没有单独隔离这些因素的贡献，"
        "不能把历史延迟直接替换进当前对照。", "",
        "**KnowLine 的两种布局实际触发了不同的内部提示策略。** 官方阈值统计“共享前缀一次 + "
        "所有问题行”的 token 数，超过 3,000 就关闭 read-twice。"
        "本批 20 个全答形状为 6,558–6,580 token，均只读一次；600 个单字段形状为 "
        "1,256–2,352 token，均将输入重复两遍后进行一次评分前向。"
        "这不是 apply/omit→Value 的两阶段决策，也不是客户端额外发出一次请求。"
        "以部署相同版本的 tokenizer 和官方源码离线重建后，三轮全部 1,860 次布局请求的"
        "评分输入 token 数都与实际响应一致，没有新增模型推理。"
        "S04 的 `t_temp` 在全答中被选为 20，在单字段中为 omit；该字段的内部提示确实不同。"
        "read-twice、内部调度与缓存同时随布局变化，本轮未做单因素消融，"
        "不能声称准确率变化完全由 read-twice 造成。"
        f"完整输入文本、阈值计数与逐条核对见[源码重建证据]({link}/knowline-layout-analysis.json)。", "",
        "**Torchcast 合并请求后没有提速。** "
        f"串行整组为 {display_ratio(torchcast['serial_tasks'])}、"
        f"平均 {torchcast['serial_wall_ms']['mean']/1000:.3f} 秒；"
        f"全答为 {display_ratio(torchcast['full_tasks'])}、"
        f"平均 {torchcast['full_ms']['mean']/1000:.3f} 秒。"
        "两种方式都在 M07 多发一键自清洁、在 M08 多发摆风角度，三轮结果一致。"
        "一次外部请求不意味着内部只做一次计算；其多字段与大候选处理路径的实际耗时"
        "需要测量，不能按减少 HTTP 次数推算速度。", "",
        "**Clef 串行修复了 M08，但需要更长时间。** "
        f"单字段为 {display_ratio(clef['layouts']['single_step_fields'])}，"
        f"串行整组为 {display_ratio(clef['layouts']['serial_tasks'])}、"
        f"平均 {clef['layouts']['serial_wall_ms']['mean']/1000:.3f} 秒；"
        f"全答为 {display_ratio(clef['layouts']['full_tasks'])}、"
        f"平均 {clef['layouts']['full_ms']['mean']/1000:.3f} 秒。"
        "三轮串行都没有多发摆风角度，全答三轮均保留这个错误。"
        f"全答英文新题为 {display_ratio(clef['quality']['validation']['original']['exact_match'])}，"
        f"中文题为 {display_ratio(clef['quality']['chinese']['original']['exact_match'])}；"
        "规范串行满分仍不能替代尚未测试的扩展题串行表现。", "",
        "**H2O 在最初三款开源模型中规范基线成绩最高，但完整请求耗时较长。** "
        f"规范为 {display_ratio(h2o['primary']['exact_match'])}，"
        f"Strands 为 {display_ratio(decider['primary']['exact_match'])}，"
        f"Liquid 为 {display_ratio(liquid['primary']['exact_match'])}。"
        f"H2O 串行整组为 {display_ratio(h2o['layouts']['serial_tasks'])}、"
        f"平均 {h2o['layouts']['serial_wall_ms']['mean']/1000:.3f} 秒；"
        f"全答为 {display_ratio(h2o['layouts']['full_tasks'])}、"
        f"平均 {h2o['layouts']['full_ms']['mean']/1000:.3f} 秒，"
        f"同批 KnowLine/Clef 全答分别为 {knowline['layouts']['full_ms']['mean']/1000:.3f}/"
        f"{clef['layouts']['full_ms']['mean']/1000:.3f} 秒。"
        f"H2O 的 {h2o['layouts']['comparable_layout_tasks']} 组可比较任务中，"
        f"{h2o['layouts']['changed_layout_tasks']} 组因布局改变了选择。"
        f"原序英文诊断为 {display_ratio(h2o['quality']['extension']['original']['exact_match'])}，"
        f"英文新题为 {display_ratio(h2o['quality']['validation']['original']['exact_match'])}，"
        f"中文题为 {display_ratio(h2o['quality']['chinese']['original']['exact_match'])}。"
        "其扩展表达表现与规范成绩、延迟需要分别比较；当前分字段评分配置的耗时"
        "不能靠合并成一次 HTTP 请求直接消除。", "",
        "按本规范验收时，模型既要选对用户要求的动作，也要对其余字段选择 omit。"
        "关闭值 0 是实际设置，与保持不变不同；摆风与自清洁等语义相近字段仍按规范标准答案验收。"
        "拆分、合并问题会改变上下文、内部调度或数值计算路径，所以必须同时检查原始选择与延迟。", "",
        "历史[五模型提示词与两阶段对照](AC_CONTROL_COMPARISON.md)、"
        "[Liquid 优化](LIQUID_AC_OPTIMIZATION.md)和[H2O 优化](H2O_OFFICIAL_OPTIMIZATION.md)"
        "分别保留。本轮统一 baseline，没有对全部九模型重跑历史五种提示词方案。"
        "两阶段先判断 apply/omit 再选择 Value，和逐字段直接选 Value/omit 的 30 步串行是不同流程。", "",
        "## 审计与复现", "",
        f"本轮共 **{result['observed_calls']:,} 次实际调用**，正式 {result['formal_calls']:,} 次、"
        f"预热 {result['warmups']} 次，接口/格式错误 {result['errors']} 次、外部请求重叠 0 次。"
        "审计逐条验证相同业务输入和顺序、模型身份、合法候选、原始响应解码、各字段覆盖与计时边界。", "",
        f"[计划]({link}/plan.json) · [逐条评分]({link}/summary.json) · [审计]({link}/audit.json) · "
        f"[基础设施与运行记录]({link}/infrastructure/) · "
        f"[实际服务适配源码]({link}/runtime_sources/) · "
        f"[15 文件运行时输入归档]({link}/runtime-input.tar.gz)", "",
        "原始 JSONL 在采集结束后以 gzip 无损归档；SHA-256 对解压后的原始字节计算。"
        "完整请求与回答示例保留可直接阅读的 JSON，重新评分程序支持两种存储格式。", "",
        "离线重新评分与生成报告：", "",
        "```bash",
        ".venv/bin/python validation/ac_control/report_all_models.py",
        "```", "",
    ]
    (PROJECT / "docs/AC_ALL_MODELS_FULL_RESULTS.md").write_text("\n".join(text))
    (root / "RESULTS.zh.md").write_text(
        "# 九模型完整统一测试\n\n[主报告](../../../../docs/AC_ALL_MODELS_FULL_RESULTS.md)\n\n"
        "[评分](summary.json) · [审计](audit.json) · [原始记录](results/)\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT)
    args = parser.parse_args()
    result = audit(args.run.resolve())
    render(args.run.resolve(), result)
    print(json.dumps({p: {"primary": m["primary"]["exact_match"],
                         "serial": m["layouts"]["serial_tasks"], "full": m["layouts"]["full_tasks"]}
                      for p, m in result["models"].items()}, ensure_ascii=False, indent=2))
