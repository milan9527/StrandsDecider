"""Audit new three-profile nine-model runs and compare quality, latency and usage."""

import argparse
import gzip
import hashlib
import json
import tarfile
from datetime import datetime
from pathlib import Path

from all_models_protocol import PROVIDERS, digest, save, sha, stamp
from analyze import grade, ratio, summarize, timing
from api_ablation_protocol import gpt_request, jev_request
from compact_input_protocol import BASELINE, VARIANTS, audit_request
from full_context_input import audit_full_context, compact_full_context
from optimized_all_models_protocol import ROOT, business_payload, portable_request
from report_all_models import NAMES, decode, expected_choices, receipt_bytes

PROJECT = Path(__file__).resolve().parents[2]


def normalized_usage(row):
    usage = (row.get("response") or {}).get("usage", {})
    if row["provider"] == "gpt":
        if "inputTokens" not in usage:
            return {}
        return {
            "input": usage["inputTokens"] + usage.get("cacheReadInputTokens", 0)
            + usage.get("cacheWriteInputTokens", 0),
            "output": usage.get("outputTokens"),
            "cache_read": usage.get("cacheReadInputTokens", 0),
            "cache_write": usage.get("cacheWriteInputTokens", 0),
        }
    return {key: usage[source] for key, source in (
        ("input", "input_tokens"), ("output", "output_tokens"),
        ("processed_input", "processed_input_tokens"),
    ) if source in usage}


def usage_summary(rows):
    usages = [normalized_usage(row) for row in rows]
    return {
        "requests": len(rows),
        **{key: {
            "observed_requests": sum(key in usage for usage in usages),
            "sum": sum(usage[key] for usage in usages if key in usage),
            "mean": (sum(usage[key] for usage in usages if key in usage)
                     / sum(key in usage for usage in usages)) if any(key in u for u in usages) else None,
        } for key in ("input", "output", "cache_read", "cache_write", "processed_input")},
    }


def audit_one(root, profile, provider):
    folder = root / "profiles" / profile
    plan = json.loads((folder / "plan.json").read_text())
    for name, checksum in plan.get("preparation_source_sha256", {}).items():
        assert digest(root / name) == checksum, name
        assert digest(Path(__file__).with_name(name)) == checksum, name
    for name, checksum in plan["input_sha256"].items():
        assert digest(folder / name) == checksum, name
    for name, checksum in plan["source_sha256"].items():
        assert digest(folder / "sources" / name) == checksum, name
        assert digest(Path(__file__).with_name(name)) == checksum, name
    assert digest(folder / "spec.md") == digest(PROJECT / "docs/AC_Control_Test_Spec.md")
    cases = {(c["case_id"], c["order"]): c for c in json.loads((folder / "cases.json").read_text())}
    original = {(c["case_id"], c["order"]): c for c in json.loads((BASELINE / "cases.json").read_text())}
    for key, case in cases.items():
        if plan.get("input_encoding") == "columnar_full_state_v2":
            assert case["payload"] == compact_full_context(original[key]["payload"])
            audit_full_context(original[key]["payload"], case["payload"])
        else:
            assert case["payload"] == portable_request(original[key]["payload"], profile)
            audit_request(original[key]["payload"], case["payload"])
    refs = {r["id"]: r for r in json.loads((folder / "references.json").read_text())}
    primary_refs = json.loads((folder / "spec_references.json").read_text())
    jobs = json.loads((folder / "schedule.json").read_text())
    planned = [(job, key) for job in jobs for key in job["keys"]]
    result_dir = folder / "results" / provider
    meta = json.loads((result_dir / "run.json").read_text())
    assert meta["status"] in ("complete", "complete_with_errors")
    assert meta["external_concurrency"] == 1 and meta["automatic_retries"] == 0
    assert meta["plan_sha256"] == digest(folder / "plan.json")
    assert meta["runner_sha256"] == plan["source_sha256"]["run_all_models.py"]
    raw = receipt_bytes(result_dir)
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == len(planned) == meta["calls"] == 2049
    assert meta["errors"] == sum(row["status"] != "ok" for row in rows)
    if provider == "gpt":
        bedrock = json.loads((result_dir / "bedrock_profile.json").read_text())
        assert bedrock["status"] == "ACTIVE" and bedrock["inferenceProfileId"] == plan["gpt_model"]
    elif provider != "jev":
        health = json.loads((result_dir / "health_before.json").read_text())
        assert health["status"] == "ok" and health["response"]["model"] == meta["expected_model"]
    timestamps = []
    request_ids = []
    for index, (row, (job, key)) in enumerate(zip(rows, planned, strict=True)):
        assert row["sequence"] == index and row["provider"] == provider and row["field"] == key
        assert all(row[name] == job[name] for name in
                   ("case_id", "dataset", "order", "language", "kind", "repetition"))
        payload = business_payload(cases[job["case_id"], job["order"]], key)
        assert row["payload"] == payload and row["input_sha256"] == sha(payload)
        transport = (gpt_request(payload) if provider == "gpt" else jev_request(payload)
                     if provider == "jev" else dict(payload, model=meta["expected_model"]))
        if provider == "h2o":
            transport["attention_mode"] = "bidirectional"
        assert row["transport_request"] == transport and row["transport_sha256"] == sha(transport)
        if provider == "gpt" and row.get("provider_error"):
            assert row["provider_error"]["ResponseMetadata"]["RetryAttempts"] == 0
        if row["status"] == "ok":
            assert row["http_status"] == 200
            choices = decode(row, provider, meta["expected_model"])
            assert choices == row["choices"]
        assert row["commands"] == [
            {"cmdKey": k, "cmdValue": v} for k, v in row.get("choices", {}).items() if v != "omit"
        ]
        assert row["started_at"] >= plan["prepared_at"]
        assert row["finished_at"] >= row["started_at"] and row["client_ms"] >= 0
        timestamps.append((row["started_at"], row["finished_at"], profile, provider, index))
        if row.get("request_id"):
            request_ids.append((provider, row["request_id"]))
    scored = [
        {**{k: row[k] for k in ("case_id", "dataset", "order", "language", "status", "client_ms", "commands")},
         "category": refs[row["case_id"]]["category"], "query": refs[row["case_id"]]["query"],
         "expected": refs[row["case_id"]]["expected"], "server_ms": row.get("server_ms"),
         **grade(refs[row["case_id"]]["expected"], row["commands"], row["status"])}
        for row in rows if row["kind"] == "quality"
    ]
    quality = {
        dataset: {order: summarize([r for r in scored if r["dataset"] == dataset and r["order"] == order])
                  for order in ("original", "reversed")}
        for dataset in ("spec", "extension", "validation", "chinese")
    }
    single_rows = [row for row in rows if row["kind"] == "serial30"]
    full_rows = [row for row in rows if row["kind"] == "full30"]
    assert len(single_rows) == 1800 and len(full_rows) == len(meta["blocks"]) == 60
    steps, layouts = [], []
    for ref in primary_refs:
        expected = expected_choices(cases[ref["id"], "original"], ref)
        for repetition in range(3):
            selected_steps = [r for r in single_rows if r["case_id"] == ref["id"] and r["repetition"] == repetition]
            full = next(r for r in full_rows if r["case_id"] == ref["id"] and r["repetition"] == repetition)
            block = next(b for b in meta["blocks"] if b["case_id"] == ref["id"] and b["repetition"] == repetition)
            assert [r["field"] for r in selected_steps] == list(expected)
            assert block["calls"] == 30 and block["artifact_operations_inside_block"] == 0
            assert abs(block["http_sum_ms"] - sum(r["client_ms"] for r in selected_steps)) < .01
            assert block["wall_ms"] >= block["http_sum_ms"]
            assert block["started_at"] <= selected_steps[0]["started_at"]
            assert selected_steps[-1]["finished_at"] <= block["finished_at"]
            combined = {k: v for row in selected_steps for k, v in row.get("choices", {}).items()}
            commands = [{"cmdKey": k, "cmdValue": v} for k, v in combined.items() if v != "omit"]
            serial_status = "ok" if all(r["status"] == "ok" for r in selected_steps) else "error"
            steps.extend({
                "case_id": ref["id"], "category": ref["category"], "repetition": repetition,
                "field": row["field"], "expected": expected[row["field"]],
                "actual": row.get("choices", {}).get(row["field"]), "status": row["status"],
                "correct": row["status"] == "ok" and row.get("choices", {}).get(row["field"]) == expected[row["field"]],
                "client_ms": row["client_ms"],
            } for row in selected_steps)
            layouts.append({
                "case_id": ref["id"], "category": ref["category"], "repetition": repetition,
                "serial_correct": grade(ref["expected"], commands, serial_status)["correct"],
                "full_correct": grade(ref["expected"], full["commands"], full["status"])["correct"],
                "serial_commands": commands, "full_commands": full["commands"],
                "serial_wall_ms": block["wall_ms"], "serial_http_sum_ms": block["http_sum_ms"],
                "full_ms": full["client_ms"], "serial_status": serial_status, "full_status": full["status"],
                "serial_input_tokens": sum(normalized_usage(r).get("input", 0) for r in selected_steps),
                "serial_token_observations": sum("input" in normalized_usage(r) for r in selected_steps),
                "full_choices": full.get("choices", {}), "serial_choices": combined,
                "full_field_hits": sum(full["status"] == "ok" and full.get("choices", {}).get(k) == v
                                       for k, v in expected.items()),
            })

    def layout_metrics(selected_layouts, selected_steps):
        return {
            "single_accuracy": ratio(sum(r["correct"] for r in selected_steps), len(selected_steps)),
            "serial_accuracy": ratio(sum(r["serial_correct"] for r in selected_layouts), len(selected_layouts)),
            "full_accuracy": ratio(sum(r["full_correct"] for r in selected_layouts), len(selected_layouts)),
            "full_field_accuracy": ratio(sum(r["full_field_hits"] for r in selected_layouts), len(selected_steps)),
            "single_ms": timing(r["client_ms"] for r in selected_steps),
            "serial_ms": timing(r["serial_wall_ms"] for r in selected_layouts),
            "full_ms": timing(r["full_ms"] for r in selected_layouts),
        }

    summary = {
        "provider": provider, "profile": profile, "model": meta["model"], "expected_model": meta["expected_model"],
        "calls": len(rows), "errors": meta["errors"], "hostname": meta["hostname"],
        "started_at": meta["started_at"], "finished_at": meta["finished_at"],
        "quality": quality, "quality_rows": scored, "layouts": layout_metrics(layouts, steps),
        "layouts_by_category": {
            category: layout_metrics([r for r in layouts if r["category"] == category],
                                     [r for r in steps if r["category"] == category])
            for category in ("single", "multi")
        },
        "layout_rows": layouts, "single_field_rows": steps,
        "tokens": {"single": usage_summary(single_rows), "full": usage_summary(full_rows),
                  "serial_input_mean": sum(r["serial_input_tokens"] for r in layouts) / len(layouts)},
        "error_rows": [{k: r.get(k) for k in
                        ("sequence", "case_id", "kind", "field", "status", "error", "provider_error")}
                       for r in rows if r["status"] != "ok"],
        "receipts_sha256": hashlib.sha256(raw).hexdigest(), "run_sha256": digest(result_dir / "run.json"),
    }
    save(result_dir / "analysis.json", summary)
    return summary, timestamps, request_ids


def archive_hashes(root, artifact, manifest):
    record = json.loads((root / manifest).read_text())
    assert digest(root / artifact) == record["sha256"]
    assert record["reference_answers_in_archive"] is False
    with tarfile.open(root / artifact) as archive:
        members = archive.getmembers()
        assert all(m.isfile() and not Path(m.name).is_absolute()
                   and ".." not in Path(m.name).parts for m in members)
        assert len(members) == len({m.name for m in members})
        assert all(Path(m.name).name not in
                   ("references.json", "spec_references.json", "spec.md") for m in members)
        actual = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in members}
    assert actual == record["files"]
    return actual


def audit_runtime(root, results):
    deployed = archive_hashes(root, "runtime-input.tar.gz", "runtime-transfer.json")
    deployed.update(archive_hashes(root, "runtime-amendment-v2.tar.gz", "runtime-amendment-v2.json"))
    for profile in VARIANTS:
        for name in ("cases.json", "models.json", "schedule.json", "plan.json"):
            relative = f"profiles/{profile}/{name}"
            assert deployed[relative] == digest(root / relative), relative
    for name, checksum in json.loads((root / "profiles/baseline/plan.json").read_text())["source_sha256"].items():
        assert deployed[name] == checksum, name
    assert deployed["full_context_input.py"] == digest(root / "full_context_input.py")
    amendment = json.loads((root / "input-amendment.json").read_text())
    assert amendment["final_profile_inference_calls_before_amendment"] == 0
    assert amendment["baseline_and_compact_catalog_unchanged"]
    assert amendment["schema_plan_sha256"] == digest(root / "profiles/schema_once/plan.json")
    assert all(m["started_at"] >= amendment["recorded_at"] for m in results["schema_once"].values())
    active = json.loads((root / "infrastructure/active_instance.json").read_text())
    assert active["instance_type"] == "g6.xlarge" and active["region"] == "us-east-1"
    local_start = min(m["started_at"] for p in results.values()
                      for provider, m in p.items() if provider not in ("jev", "gpt"))
    for name in ("prepare-us-east-runtimes", "apply-full-context-input-amendment"):
        operation = json.loads((root / "operations" / (name + ".json")).read_text())
        status = json.loads((root / "operations" / (name + ".status.json")).read_text())
        assert operation["instance"] == active["instance_id"] and operation["region"] == active["region"]
        assert operation["script_sha256"] == digest(root / "operations" / (name + ".sh"))
        assert status["Status"] == "Success" and status["ResponseCode"] == 0
        assert datetime.fromisoformat(status["ExecutionEndDateTime"]) <= datetime.fromisoformat(local_start)
    verification = json.loads((root / "logs/model-verification.json").read_text())
    for provider in ("liquid", "pplx", "knowline", "torchcast", "clef", "h2o"):
        assert verification[provider]["revision"] == results["baseline"][provider]["model"]["revision"]
        manifest = json.loads((root / "logs/model-manifests" / (provider + ".json")).read_text())
        assert manifest["revision"] == verification[provider]["revision"]
        assert len(manifest["files"]) == verification[provider]["verified_files"]
    integrity = json.loads((root / "logs/strands-model-integrity.json").read_text())
    assert integrity["status"] == "ok" and integrity["files_verified"] == 9
    overlay = json.loads((root / "logs/h2o-overlay-verification.json").read_text())
    assert len(overlay) == 30
    assert overlay == json.loads((root / "logs/h2o-overlay-rechecked.json").read_text())
    return {"active_instance": active, "deployed_file_hashes": deployed,
            "model_verification": verification, "input_amendment": amendment}


def audit_predecessor(root):
    """Preserve exploratory calls in the complete chronology, outside final scores."""
    folder = root / "attempts/schema-once-distributed-v1"
    plan = json.loads((folder / "plan.json").read_text())
    for name, checksum in plan["input_sha256"].items():
        assert digest(folder / name) == checksum
    result_dir = folder / "results/jev"
    meta = json.loads((result_dir / "run.json").read_text())
    raw = receipt_bytes(result_dir)
    rows = [json.loads(line) for line in raw.splitlines()]
    assert meta["status"] == "complete" and len(rows) == meta["calls"] == 2049
    assert meta["plan_sha256"] == digest(folder / "plan.json")
    assert meta["automatic_retries"] == 0 and meta["external_concurrency"] == 1
    assert all(r["status"] == "ok" and decode(r, "jev", meta["expected_model"]) == r["choices"] for r in rows)
    intervals = [(r["started_at"], r["finished_at"], "predecessor", "jev", r["sequence"]) for r in rows]
    ids = [("jev", r["request_id"]) for r in rows if r.get("request_id")]
    return {"calls": len(rows), "provider": "jev", "included_in_final_scores": False,
            "receipts_sha256": hashlib.sha256(raw).hexdigest(),
            "path": str(folder.relative_to(root))}, intervals, ids


def audit(root, partial=False):
    results = {}
    timestamps, ids = [], []
    for profile in VARIANTS:
        results[profile] = {}
        for provider in PROVIDERS:
            path = root / "profiles" / profile / "results" / provider / "run.json"
            if partial and (not path.exists() or json.loads(path.read_text())["status"] not in
                            ("complete", "complete_with_errors")):
                continue
            summary, intervals, request_ids = audit_one(root, profile, provider)
            results[profile][provider] = summary
            timestamps.extend(intervals)
            ids.extend(request_ids)
    timestamps.sort()
    assert all(datetime.fromisoformat(a[1]) <= datetime.fromisoformat(b[0])
               for a, b in zip(timestamps, timestamps[1:])), "Overlapping external requests"
    assert len(ids) == len(set(ids)), "Duplicate hosted request IDs"
    local_hosts = {m["hostname"] for profiles in results.values() for p, m in profiles.items()
                   if p not in ("jev", "gpt")}
    assert len(local_hosts) <= 1
    result = {"generated_at": stamp(), "complete": not partial, "profiles": results,
              "completed_profile_models": sum(len(v) for v in results.values()),
              "calls": len(timestamps), "overlap_count": 0, "unique_reported_request_ids": len(ids),
              "local_hosts": sorted(local_hosts), "auditor_sha256": digest(Path(__file__))}
    if not partial:
        assert result["completed_profile_models"] == 27 and result["calls"] == 55323
        result["runtime_audit"] = audit_runtime(root, results)
        predecessor, earlier, earlier_ids = audit_predecessor(root)
        all_intervals = sorted(timestamps + earlier)
        assert all(datetime.fromisoformat(a[1]) <= datetime.fromisoformat(b[0])
                   for a, b in zip(all_intervals, all_intervals[1:]))
        assert len(ids + earlier_ids) == len(set(ids + earlier_ids))
        result["predecessor"] = predecessor
        result["total_calls_including_predecessor"] = len(all_intervals)
    save(root / ("progress-summary.json" if partial else "summary.json"), result)
    return result


def render(root, result):
    assert result["complete"]
    profiles = result["profiles"]
    active = json.loads((root / "infrastructure/active_instance.json").read_text())
    link = "../validation/ac_control/runs/" + root.name

    def accuracy(metric):
        return f"{metric['numerator']}/{metric['denominator']}（{metric['rate']*100:.1f}%）"

    def cell(profile, provider, layout):
        metrics = profiles[profile][provider]["layouts"]
        divisor = 1 if layout == "single" else 1000
        unit = "ms" if layout == "single" else "秒"
        return f"{accuracy(metrics[layout + '_accuracy'])} / {metrics[layout + '_ms']['mean']/divisor:.3f} {unit}"

    lines = [
        "# 空调控制九模型输入压缩完整实测", "",
        "按 [AC_Control_Test_Spec.md](AC_Control_Test_Spec.md) 重跑全部九模型，"
        "比较原始输入与两种压缩表示。27 组均完成，每组 2,049 次新调用，合计 55,323 次；"
        "全局外部并发为 1，无自动重试和答案修复。", "",
        "另保留第二种压缩表示的早期 Jev 试跑 2,049 次，共计实际调用 57,372 次。"
        "检查服务实现后发现，逐字段评分服务需要在公共状态中读取完整能力表，因此在其他模型测试该版本前，"
        "将跨问题分散的映射改为公共状态中的紧凑表，并补测 Jev。早期试跑不计入下列对照；"
        "原始输入与第一种压缩方案未改动。修订原因、前后输入及原始回执均已保留。", "",
        f"本地七模型在同一台独占 `{active['instance_type']}` / L4（`{active['region']}`，"
        f"`{active['availability_zone']}`）上依次运行。Jev 和 GPT 沿用美东托管 API 客户端；"
        "其内部硬件与本地 GPU 不同。GPT 固定 GPT 6.1 Sol、low effort。", "",
        "## 输入与判分", "",
        "- baseline：原始完整能力表、字段说明及选项描述。",
        "- compact_catalog：保留原始能力表，集中公共规则，精简字段及选项描述。",
        "- schema_once：完整能力表在 state 中使用列名加数据行的紧凑表示，问题与 compact_catalog 相同。"
        "每个内部评分任务都能读取完整映射。",
        "- 全部版本保留 30 项能力和 283 个现有候选（含每字段一个 omit，共 30 个）；"
        "数值范围沿用整数候选，范围单位、状态限制与温标伴随规则不变。",
        "- 九模型统一使用字符串选项描述；数值描述为数值 ID，与此前 Clef 专用 None 描述的离线版本不同。",
        "- 按整条命令集合严格判分；多发、漏发、错误值均失败。单字段准确率与完整任务准确率分开。",
        "- 大多数未要求字段应选 omit，因而单字段准确率可能很高；判断是否满足控制需求，应看完整任务准确率。",
        "- 单步：一次请求选择一个字段；30 步串行：对同一个 Query 依次请求全部 30 个字段，"
        "合并成一条命令集合，不把上一字段答案传给下一步；一次全答：一次提交全部 30 个字段。"
        "三者均保留完整能力集，串行不是连续执行 30 条不同用户指令。",
        "- 每个版本测试 20 个规范场景，每种布局重复三轮；60 次完整任务对应 20 个不同场景。",
        "- 每版本另有 156 次质量请求，含规范、诊断、英文改写和中文对应题，以及两种选项顺序。",
        "- 原始输入也重新实测；不同版本的运行顺序按模型轮换，保留原生缓存与相同预热流程。", "",
    ]
    lines += ["## 压缩收益与准确率变化", "",
              "同一模型相对本轮 baseline；耗时和 tokens 的负数表示下降，准确率变化单位为百分点。"
              "每列使用整个版本的成绩，不按题目拼接最好答案。", "",
              "| 模型 / 输入 | 全答准确率变化 | 全答耗时变化 | 全答 tokens 变化 | 串行准确率变化 | 串行耗时变化 |",
              "|---|---:|---:|---:|---:|---:|"]
    for provider in PROVIDERS:
        baseline = profiles["baseline"][provider]
        for profile in VARIANTS[1:]:
            model = profiles[profile][provider]
            before, after = baseline["layouts"], model["layouts"]
            token_before = baseline["tokens"]["full"]["input"]["mean"]
            token_after = model["tokens"]["full"]["input"]["mean"]
            tokens = f"{(token_after/token_before - 1)*100:+.1f}%" if token_before and token_after is not None else "未报告"
            lines.append(
                f"| {NAMES[provider]} / {profile} | "
                f"{(after['full_accuracy']['rate'] - before['full_accuracy']['rate'])*100:+.1f} | "
                f"{(after['full_ms']['mean']/before['full_ms']['mean'] - 1)*100:+.1f}% | {tokens} | "
                f"{(after['serial_accuracy']['rate'] - before['serial_accuracy']['rate'])*100:+.1f} | "
                f"{(after['serial_ms']['mean']/before['serial_ms']['mean'] - 1)*100:+.1f}% |"
            )
    lines.append("")
    for layout, title in (("full", "一次回答全部 30 字段"), ("single", "单步决策"),
                          ("serial", "30 步串行")):
        lines += [f"## {title}：准确率 / 平均耗时", "",
                  "| 模型 | baseline | compact_catalog | schema_once |",
                  "|---|---:|---:|---:|"]
        for provider in PROVIDERS:
            lines.append("| " + NAMES[provider] + " | "
                         + " | ".join(cell(profile, provider, layout) for profile in VARIANTS) + " |")
        lines.append("")
    lines += ["## 一次全答的 API 报告输入 tokens", "",
              "下表比较同一模型各输入版本。不同服务的 usage 口径不同：有的累计逐题处理，"
              "有的报告共享序列长度，因此跨模型绝对值不等于相同计算量。GPT 输入包含普通输入、"
              "缓存读取与缓存写入；H2O 的 processed_input_tokens 另存于核算文件。", "",
              "| 模型 | baseline | compact_catalog | schema_once |", "|---|---:|---:|---:|"]
    for provider in PROVIDERS:
        values = [profiles[p][provider]["tokens"]["full"]["input"]["mean"] for p in VARIANTS]
        lines.append("| " + NAMES[provider] + " | "
                     + " | ".join("未报告" if v is None else f"{v:,.1f}" for v in values) + " |")
    lines += ["", "## 扩展表达准确率", "",
              "中文只翻译用户 Query，规则与能力说明保持英文。题目沿用既有冻结题，"
              "不属于新的独立盲测。下表使用原始选项顺序。", "",
              "| 模型 / 输入 | 规范 20 题 | 诊断 10 题 | 英文改写 24 题 | 中文 24 题 |",
              "|---|---:|---:|---:|---:|"]
    for provider in PROVIDERS:
        for profile in VARIANTS:
            quality = profiles[profile][provider]["quality"]
            lines.append(f"| {NAMES[provider]} / {profile} | "
                         + " | ".join(accuracy(quality[d]["original"]["exact_match"])
                                      for d in ("spec", "extension", "validation", "chinese")) + " |")
    lines += ["", "## 接口与审计", "",
              "| 模型 | baseline 错误数 | compact_catalog 错误数 | schema_once 错误数 |",
              "|---|---:|---:|---:|"]
    for provider in PROVIDERS:
        lines.append("| " + NAMES[provider] + " | "
                     + " | ".join(str(profiles[p][provider]["errors"]) for p in VARIANTS) + " |")
    lines += ["", "接口失败保留在准确率分母中。耗时表包含全部正式请求，预热单列；"
              "30 步串行计时不含文件写入或归档。完整核算包含均值、p50、p95、最大值、"
              "单指令/多指令、逐字段、逐题错误、缓存 usage 和原始响应。", "",
              "本轮仅改变输入表示，各服务内部仍沿用原有实现。逐字段评分、共享前缀缓存、联合决策头、"
              "大候选分组等路径不同，所以减少相同比例的输入不保证相同比例的加速。"
              "保留完整映射只能保证任务信息未丢失，不能保证模型理解新表示的能力不下降。"
              "这里的百分比属于这 20 个既有规范场景；三次重复不是 60 个独立新场景，"
              "不能据此声称生产环境准确率或泛化能力已得到保证。", "",
              f"[全部核算结果]({link}/summary.json) · [初始测试计划]({link}/plan.json) · "
              f"[第二版本修订记录]({link}/input-amendment.json) · "
              "[输入设计与规范依据](AC_DECISION_INPUT_OPTIMIZATION.md) · "
              "[上一轮九模型部署与完整结果](AC_ALL_MODELS_FULL_RESULTS.md)", "",
              "复现最终输入文件（不发起模型调用，输出目录须不存在）：", "",
              "```bash",
              "python validation/ac_control/prepare_optimized_inputs.py --run /path/to/new-run",
              "```", ""]
    path = PROJECT / "docs/AC_ALL_MODELS_INPUT_OPTIMIZATION_RESULTS.md"
    path.write_text("\n".join(lines))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    result = audit(args.run, args.partial)
    if not args.partial:
        render(args.run, result)
    print(json.dumps({k: v for k, v in result.items() if k != "profiles"}, indent=2))
