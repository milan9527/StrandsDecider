"""Audit the API serial extension and report whole-task versus per-Key time."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze import timing
from api_ablation_protocol import decode_gpt, decode_jev, gpt_request, jev_request
from run_api_serial_latency import digest, schedule
from run_resident import save, sha

LABELS = {
    "decider": "Strands Decider", "liquid": "Liquid d1-2B", "h2o": "H2O Lightning 4B",
    "jev": "Jev 1.14.0", "gpt": "GPT 6.1 Sol low",
}


def analyze(run):
    plan = json.loads((run / "plan.json").read_text())
    parent = run.parent / plan["parent_run_name"]
    api_parent = run.parent / plan["api_parent_run_name"]
    for name, expected in plan["parent_files_sha256"].items():
        assert digest(parent / name) == expected, name
    assert digest(api_parent / "plan.json") == plan["api_parent_plan_sha256"]
    for name, expected in plan["source_sha256"].items():
        assert digest(run / "sources" / name) == expected, name
        assert digest(Path(__file__).with_name(name)) == expected, name
    payload = json.loads((run / "payload.json").read_text())
    assert sha(payload) == plan["payload_sha256"]
    assert (run / "payload.json").read_bytes() == (parent / "payload.json").read_bytes()
    metadata = json.loads((run / "run.json").read_text())
    assert metadata["status"] in ("complete", "complete_with_errors")
    assert metadata["plan_sha256"] == digest(run / "plan.json")
    rows = [json.loads(line) for line in (run / "receipts.jsonl").read_text().splitlines()]
    scheduled = [(p, rep, mode, task) for p in plan["providers"]
                 for rep, mode, task in schedule(payload, plan["repetitions"])]
    assert len(rows) == len(scheduled) == metadata["actual_calls"] == 188
    for row, (provider, repetition, mode, task) in zip(rows, scheduled, strict=True):
        assert (row["provider"], row["repetition"], row["mode"]) == (provider, repetition, mode)
        assert row["warmup"] == (repetition == -1)
        assert row["question_ids"] == list(task["questions"])
        assert row["payload"] == task and row["input_sha256"] == sha(task)
        request = gpt_request(task) if provider == "gpt" else jev_request(task)
        assert row["transport_request"] == request and row["transport_sha256"] == sha(request)
        assert datetime.fromisoformat(row["started_at"]) <= datetime.fromisoformat(row["finished_at"])
        if provider == "gpt":
            retries = row.get("response", {}).get("ResponseMetadata", {}).get("RetryAttempts")
            assert retries in (None, 0), retries
        if row["status"] == "ok":
            assert row["http_status"] == 200
            if provider == "jev":
                assert row["response"] == json.loads(row["response_text"])
                decoded = decode_jev(row["response"], task, plan["jev_expected_response_model"])
            else:
                decoded = decode_gpt(row["response"], task)
            assert row["choices"] == decoded
    for first, second in zip(rows[:-1], rows[1:], strict=True):
        assert datetime.fromisoformat(first["finished_at"]) <= datetime.fromisoformat(second["started_at"])
    previous_rows = [json.loads(line) for line in (parent / "receipts.jsonl").read_text().splitlines()]
    assert datetime.fromisoformat(previous_rows[-1]["finished_at"]) < datetime.fromisoformat(rows[0]["started_at"])
    models = {}
    for provider in plan["providers"]:
        group = [r for r in rows if r["provider"] == provider and not r["warmup"]]
        measurements = []
        for repetition in range(plan["repetitions"]):
            full = [r for r in group if r["repetition"] == repetition and r["mode"] == "full_30"]
            single = [r for r in group if r["repetition"] == repetition and r["mode"] == "serial_1"]
            assert len(full) == 1 and len(single) == 30
            assert [r["question_ids"][0] for r in single] == list(payload["questions"])
            combined = {k: v for r in single for k, v in r.get("choices", {}).items()}
            all_valid = full[0]["status"] == "ok" and all(r["status"] == "ok" for r in single)
            elapsed = (datetime.fromisoformat(single[-1]["finished_at"])
                       - datetime.fromisoformat(single[0]["started_at"])).total_seconds() * 1000
            measurements.append({
                "repetition": repetition, "full_30_client_ms": full[0]["client_ms"],
                "serial_30_client_sum_ms": sum(r["client_ms"] for r in single),
                "serial_30_wall_ms": elapsed, "all_responses_valid": all_valid,
                "changed_keys": ([k for k in combined if combined[k] != full[0]["choices"][k]]
                                 if all_valid else None),
                "full_choices": full[0].get("choices"), "serial_choices": combined,
                "full_usage": full[0].get("response", {}).get("usage"),
            })
        models[provider] = {
            "full_30_ms": timing(m["full_30_client_ms"] for m in measurements),
            "single_question_ms": timing(r["client_ms"] for r in group if r["mode"] == "serial_1"),
            "serial_30_wall_ms": timing(m["serial_30_wall_ms"] for m in measurements),
            "server_full_30_ms": timing(r.get("server_ms") for r in group if r["mode"] == "full_30"),
            "server_single_question_ms": timing(r.get("server_ms") for r in group if r["mode"] == "serial_1"),
            "formal_errors": sum(r["status"] != "ok" for r in group),
            "per_key": {key: {
                "client_ms": timing(r["client_ms"] for r in group if r["question_ids"] == [key]),
                "choices": [r.get("choices", {}).get(key) for r in group if r["question_ids"] == [key]],
            } for key in payload["questions"]},
            "native_usage_totals_by_mode": {mode: {
                key: sum(r.get("response", {}).get("usage", {}).get(key, 0) or 0
                         for r in group if r["mode"] == mode)
                for key in sorted({
                    k for r in group if r["mode"] == mode
                    for k, value in r.get("response", {}).get("usage", {}).items()
                    if isinstance(value, (int, float))
                })
            } for mode in plan["modes"]},
            "measurements": measurements,
        }
    summary = {
        "case_id": plan["case_id"], "repetitions": plan["repetitions"],
        "formal_http_calls": 186, "warmup_http_calls": 2,
        "errors": sum(r["status"] != "ok" for r in rows),
        "request_overlap_count": 0, "model_windows_overlap": False,
        "all_five_model_windows_overlap": False, "same_client_host_as_gpu_diagnostic": False,
        "same_full_state_and_candidate_values_verified": True,
        "receipts_sha256": digest(run / "receipts.jsonl"),
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "models": models,
    }
    save(run / "summary.json", summary)
    previous = json.loads((parent / "summary.json").read_text())
    combined = {**previous["models"], **models}
    save(run / "five_model_summary.json", {
        "case_id": plan["case_id"], "formal_http_calls": 465, "warmup_http_calls": 5,
        "errors": summary["errors"], "all_five_model_windows_overlap": False,
        "separate_chronological_runs": [parent.name, run.name], "models": combined,
    })
    text = [
        "# 空调单步决策与总体耗时：Jev / GPT 串行补测", "",
        "延续三个GPU模型的S03基线诊断，业务输入逐字节相同。"
        "沿用原API测试的客户端主机依次执行Jev、GPT，Jev完成后才开始GPT；"
        "各模型预热1次，每模式正式重复3轮，模式顺序交替。GPT保持low effort及原固定JSON格式提示。", "",
        "> " + json.loads(payload["state"])["query"], "",
        "- 单步决策：一个请求只回答一个Key，保留完整30项能力状态和该题全部原始候选。",
        "- 30步串行总时间：每一步返回后才发下一步，测量首步开始至第30步结束，包含中间记录开销。",
        "- 一次回答30题：一个请求携带全部问题，测量收到完整回答的时间。", "",
        "| 模型 | 单步均值 ms | 单步P95 ms | 30步串行总时间均值 ms | 一次回答30题均值 ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for provider, data in combined.items():
        text.append(f"| {LABELS[provider]} | {data['single_question_ms']['mean']:.1f} | "
                    f"{data['single_question_ms']['p95']:.1f} | "
                    f"{data['serial_30_wall_ms']['mean']:.1f} | {data['full_30_ms']['mean']:.1f} |")
    text += [
        "", "各模型单步统计来自90次实际请求，完整请求统计来自3次请求。"
        "它们是同一个Query内30种不同Key的重复测量，并非90个独立业务场景。"
        "三个GPU模型复用前一轮已审计记录，Jev/GPT本轮新增186次正式调用和2次预热；"
        f"本轮错误数为{summary['errors']}。五模型合计465次正式调用、5次预热，"
        "保存的请求与模型运行时间区间均无重叠。", "",
        "上述数字为客户端耗时：GPU服务走本机loopback，Jev走HTTPS，GPT走Bedrock。"
        "业务输入和串行规则相同，GPU与API测试客户端主机不同；"
        "模型硬件、网络、服务实现与缓存也不同。"
        "预热不计入统计，未显式配置提示缓存；原生usage完整保留。Jev未返回服务端耗时。", "",
        "## 拆分后的回答", "",
    ]
    for provider, data in models.items():
        text.append("- " + LABELS[provider] + "：" + "；".join(
            f"第{m['repetition'] + 1}轮改变{len(m['changed_keys'])}个Key"
            if m["changed_keys"] is not None else f"第{m['repetition'] + 1}轮存在无效响应"
            for m in data["measurements"]) + "。")
    text += [
        "", "这是一道固定Query的延迟与输出一致性诊断，不替代原20题正确率。"
        "前三模型中Liquid拆分后每轮6个Key选择改变；其原准确率属于完整30题请求。", "",
        "## 各Key实测时间", "",
        "| Key | Jev均值 ms | GPT均值 ms | Jev三轮选择 | GPT三轮选择 |",
        "|---|---:|---:|---|---|",
    ]
    for key in payload["questions"]:
        j, g = (models[p]["per_key"][key] for p in ("jev", "gpt"))
        text.append(f"| `{key}` | {j['client_ms']['mean']:.1f} | {g['client_ms']['mean']:.1f} | "
                    f"{', '.join(str(v) for v in j['choices'])} | {', '.join(str(v) for v in g['choices'])} |")
    text += [
        "", "[冻结计划](plan.json) · [完整输入](payload.json) · [请求与原始回答](receipts.jsonl) · "
        "[逐次指标及usage](summary.json) · [五模型合并指标](five_model_summary.json) · "
        f"[前三模型补测](../{parent.name}/LATENCY.zh.md)。", "",
    ]
    (run / "LATENCY.zh.md").write_text("\n".join(text))
    print(json.dumps({p: {k: v for k, v in d.items() if k not in (
        "measurements", "per_key", "native_usage_totals_by_mode",
    )} for p, d in models.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    analyze(parser.parse_args().run)
