"""Audit a complete GPT rerun against the frozen nine-model AC benchmark."""

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from all_models_protocol import digest, save, stamp
from analyze import display_ratio
from report_all_models import PROJECT, audit, receipt_bytes

DEFAULT = Path(__file__).parent / "runs/2026-10-31-gpt-retest-v1"


def report(root):
    manifest = json.loads((root / "retest.json").read_text())
    parent = PROJECT / manifest["parent_run"]
    assert manifest["providers"] == ["gpt"] and manifest["automatic_retries"] == 0
    assert digest(parent / "plan.json") == manifest["parent_plan_sha256"] == digest(root / "plan.json")
    assert digest(parent / "results/gpt/run.json") == manifest["parent_gpt_run_sha256"]
    for name, checksum in manifest["copied_files_sha256"].items():
        assert digest(root / name) == digest(parent / name) == checksum, name
    result = audit(root, providers=("gpt",), write=False)
    model = result["models"]["gpt"]
    old = json.loads((parent / "summary.json").read_text())["models"]["gpt"]
    prior_raw = receipt_bytes(parent / "results/gpt")
    assert hashlib.sha256(prior_raw).hexdigest() == manifest["parent_gpt_receipts_sha256"]
    assert old["evidence"]["receipts_sha256"] == manifest["parent_gpt_receipts_sha256"]
    prior = [json.loads(line) for line in prior_raw.splitlines()]
    folder = root / "results/gpt"
    raw = receipt_bytes(folder)
    rows = [json.loads(line) for line in raw.splitlines()]
    for previous, current in zip(prior, rows, strict=True):
        for key in ("sequence", "case_id", "kind", "field", "repetition", "order",
                    "payload", "input_sha256", "transport_request", "transport_sha256"):
            assert previous[key] == current[key], (key, current["sequence"])
    request_ids = [r.get("request_id") for r in rows]
    old_ids = {r.get("request_id") for r in prior if r.get("request_id")}
    successful = [r for r in rows if r["status"] == "ok"]
    retries = [r["response"]["ResponseMetadata"]["RetryAttempts"] for r in successful]
    clean = (
        model["errors"] == 0 and len(successful) == 2049
        and all(r["http_status"] == 200 for r in successful)
        and retries == [0] * 2049
        and all(request_ids) and len(set(request_ids)) == 2049
        and not old_ids.intersection(request_ids)
    )
    same_host = old["hostname"] == model["hostname"]
    audit_result = {k: v for k, v in result.items() if k != "models"} | {
        "clean_interface_run": clean,
        "parent_run": manifest["parent_run"],
        "parent_plan_sha256": manifest["parent_plan_sha256"],
        "same_client_hostname": same_host,
        "same_ordered_transport_requests_as_parent": True,
        "unique_request_ids": len({i for i in request_ids if i}),
        "request_ids_reused_from_parent": len(old_ids.intersection(request_ids)),
        "http_status_counts": dict(Counter(str(r.get("http_status")) for r in rows)),
        "successful_response_sdk_retry_counts": dict(Counter(map(str, retries))),
        "retest_manifest_sha256": digest(root / "retest.json"),
        "retest_reporter_sha256": digest(Path(__file__)),
        "evidence": {"gpt": model["evidence"]},
    }
    save(root / "summary.json", result)
    save(root / "audit.json", audit_result)
    sources = root / "analysis_sources"
    sources.mkdir(exist_ok=True)
    for name in (*result["grading_sources_sha256"], Path(__file__).name):
        (sources / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    checks = []
    for previous in old["error_rows"]:
        row = rows[previous["sequence"]]
        scored = next(r for r in model["single_step_checks"]
                      if r["case_id"] == row["case_id"] and r["repetition"] == row["repetition"]
                      and r["key"] == row["field"])
        checks.append({
            "sequence": row["sequence"], "case_id": row["case_id"],
            "repetition": row["repetition"], "field": row["field"],
            "previous_status": previous["status"], "current_status": row["status"],
            "current_correct": scored["correct"],
            "expected": scored["expected"], "actual": scored["actual"],
            "request_id": row.get("request_id"),
        })
    save(root / "previous-error-positions.json", checks)
    compare = {"generated_at": stamp(), "previous": old, "retest": model,
               "clean_interface_run": clean, "previous_error_positions": checks}
    save(root / "comparison.json", compare)
    compressed = gzip.compress(raw, mtime=0)
    assert gzip.decompress(compressed) == raw
    archive = folder / "receipts.jsonl.gz"
    archive.write_bytes(compressed)
    assert gzip.decompress(archive.read_bytes()) == raw
    save(root / "receipt-archive.json", {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "gzip_sha256": digest(archive), "raw_bytes": len(raw),
        "gzip_bytes": len(compressed), "roundtrip_verified": True,
    })
    plain = folder / "receipts.jsonl"
    if plain.exists():
        plain.unlink()
    render(root, old, model, audit_result, checks)
    return audit_result


def render(root, old, model, audit_result, checks):
    link = "../validation/ac_control/runs/" + root.name
    clean = audit_result["clean_interface_run"]
    text = [
        "# GPT 空调控制完整重测", "",
        f"测试日期：{model['evidence']['started_at'][:10]}（UTC）。"
        "针对[九模型统一测试](AC_ALL_MODELS_FULL_RESULTS.md)中 GPT 的三次接口异常，"
        "重新执行全部冻结请求。模型仍为 `us.openai.gpt-6.1-sol`、low effort，"
        "Bedrock Converse、美国区域、8192 输出 token 上限；输入、选项、提示词、"
        "调用顺序和推理源码与原轮完全一致。", "",
        (f"**本轮 {model['calls']:,} 次调用全部成功，接口及格式异常为 0，"
         "SDK 自动重试为 0，请求重叠为 0。**" if clean else
         f"**本轮完成 {model['calls']:,} 次调用，仍有 {model['errors']} 次异常；"
         "未达到整轮无异常的目标。全部失败均保留。**"), "",
        "本次独立重跑，不替换原轮的失败记录，不用成功重试覆盖失败。"
        "九模型原表仍对应 2026-10-30 的完整运行，本页单列 GPT 新一轮结果。", "",
        "## 三种请求方式", "",
        "规范全部 20 条指令各三轮：1,800 次单字段调用组成 60 个串行任务，"
        "另有 60 次全答。单步按字段评分；串行、全答按整组命令严格匹配评分。"
        "60 个任务来自 20 题重复三轮，不是 60 道独立新题。", "",
        "| 请求方式 | 原轮准确率 | 重测准确率 | 原轮平均耗时 | 重测平均耗时 | 重测 P95 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, score, time_key, scale, unit in (
        ("单步决策", "single_step_fields", "single_step_ms", 1, "ms"),
        ("30 步串行", "serial_tasks", "serial_wall_ms", 1000, "秒"),
        ("一次全答", "full_tasks", "full_ms", 1000, "秒"),
    ):
        before, after = old["layouts"], model["layouts"]
        text.append(
            f"| {label} | {display_ratio(before[score])} | {display_ratio(after[score])} | "
            f"{before[time_key]['mean']/scale:.3f} {unit} | "
            f"{after[time_key]['mean']/scale:.3f} {unit} | {after[time_key]['p95']/scale:.3f} {unit} |")
    text += [
        "", f"规范主成绩（20 条原序全答各一次）：原轮 "
        f"{display_ratio(old['primary']['exact_match'])}，重测 "
        f"{display_ratio(model['primary']['exact_match'])}。"
        f"重测规范完整请求均值 {model['primary']['client_ms']['mean']/1000:.3f} 秒。", "",
        "| 原异常位置 | 字段 | 重测响应 | 重测选择正确 |", "|---|---|---|---|",
    ]
    for row in checks:
        text.append(f"| {row['case_id']} / 第 {row['repetition']+1} 轮 | `{row['field']}` | "
                    f"{row['current_status']} | {'是' if row['current_correct'] else '否'} |")
    text += [
        "", "以上三处只用于核对原异常位置；本次实际重跑了全部 2,049 次请求。", "",
        "## 质量附项", "",
        "| 数据集 | 原轮原序 / 反序 | 重测原序 / 反序 |", "|---|---|---|",
    ]
    for key, label in (("spec", "规范 20 题"), ("extension", "英文诊断 10 题"),
                       ("validation", "英文新题 24 题"), ("chinese", "中文翻译 24 题")):
        scores = [" / ".join(display_ratio(m["quality"][key][order]["exact_match"])
                             for order in ("original", "reversed")) for m in (old, model)]
        text.append(f"| {label} | {scores[0]} | {scores[1]} |")
    text += [
        "", "## 计时与审计", "",
        "总计 2,049 次：156 次质量请求、1,800 次单字段、60 次全答、33 次预热。"
        "外部并发为 1，客户端与 SDK 均不自动重试；失败仍留在准确率分母。"
        "30 步总时间实际测量，整组计时结束后才写盘。", "",
        f"本轮脚本总墙钟 {model['run_timing']['wall_seconds']/60:.2f} 分钟，"
        f"全部请求计时之和 {model['run_timing']['all_request_seconds']/60:.2f} 分钟；"
        "包含扩展题和预热，不能用作单条空调指令的响应时间。"
        f"调用客户端主机{'与原轮相同' if audit_result['same_client_hostname'] else '与原轮不同'}。"
        "两轮测试日期不同，服务负载和缓存状态未固定，"
        "时间变化不能仅归因于接口异常消失。", "",
        "离线逐条检查冻结输入、原始响应解码、模型标识、low effort、合法选项、"
        "HTTP 状态、SDK 重试次数、完整覆盖和时间区间。"
        f"本轮请求 ID 去重后 {audit_result['unique_request_ids']:,} 个，"
        f"与原轮重复 {audit_result['request_ids_reused_from_parent']} 个。"
        "整轮无异常只描述这次观测，不代表托管接口今后不会出现瞬时故障。", "",
        f"[重测计划]({link}/retest.json) · [审计]({link}/audit.json) · "
        f"[逐条评分]({link}/summary.json) · [两轮对照]({link}/comparison.json) · "
        f"[原异常位置核对]({link}/previous-error-positions.json) · "
        f"[完整原始请求与回答（gzip）]({link}/results/gpt/receipts.jsonl.gz)", "",
        "离线复核（不会调用模型）：", "",
        "```bash", ".venv/bin/python validation/ac_control/report_gpt_retest.py", "```", "",
    ]
    (PROJECT / "docs/AC_GPT_RETEST_RESULTS.md").write_text("\n".join(text))
    (root / "REPORT.zh.md").write_text(
        "# GPT 完整重测\n\n详细结果见[GPT 空调控制完整重测]"
        "(../../../../docs/AC_GPT_RETEST_RESULTS.md)。\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT)
    result = report(parser.parse_args().run)
    print(json.dumps({k: result[k] for k in (
        "passed", "observed_calls", "errors", "overlap_count", "clean_interface_run")}, indent=2))
    raise SystemExit(0 if result["clean_interface_run"] else 1)
