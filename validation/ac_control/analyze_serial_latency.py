"""Audit the serial diagnostic and separate per-choice from whole-task latency."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from analyze import timing
from compare_resident import LABELS
from run_ablation import MODELS, choices
from run_resident import save, sha


def analyze(run):
    plan = json.loads((run / "plan.json").read_text())
    payload = json.loads((run / "payload.json").read_text())
    assert sha(payload) == plan["payload_sha256"]
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((run / "sources" / name).read_bytes()).hexdigest() == digest
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest
    assert json.loads((run / "complete.json").read_text())["status"] == "complete"
    before = json.loads((run / "before_environment.json").read_text())
    after = json.loads((run / "after_environment.json").read_text())
    assert before["services"]["stdout"] == after["services"]["stdout"]
    rows = [json.loads(s) for s in (run / "receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 3 * (1 + 3 * (1 + 30))
    for row in rows:
        task = (payload if row["mode"] == "full_30" else {
            "state": payload["state"],
            "questions": {k: payload["questions"][k] for k in row["question_ids"]},
        })
        assert row["question_ids"] == list(task["questions"])
        assert len(task["questions"]) == (30 if row["mode"] == "full_30" else 1)
        assert row["input_sha256"] == sha(task)
        assert row["status"] == "ok" and row["http_status"] == 200
        assert row["response"] == json.loads(row["response_text"])
        assert row["choices"] == choices(row["response"], task, MODELS[row["provider"]]["id"])
    for first, second in zip(rows[:-1], rows[1:], strict=True):
        assert datetime.fromisoformat(first["finished_at"]) <= datetime.fromisoformat(second["started_at"])
    provider_order = list(dict.fromkeys(r["provider"] for r in rows))
    assert provider_order == plan["providers"]
    assert [r["provider"] for r in rows] == [
        p for p in provider_order for _ in range(1 + 3 * 31)
    ]
    groups = {}
    for provider in plan["providers"]:
        group = [r for r in rows if r["provider"] == provider and not r["warmup"]]
        measurements = []
        for repetition in range(plan["repetitions"]):
            full = [r for r in group if r["repetition"] == repetition and r["mode"] == "full_30"]
            single = [r for r in group if r["repetition"] == repetition and r["mode"] == "serial_1"]
            assert len(full) == 1 and len(single) == 30
            assert [r["question_ids"][0] for r in single] == list(payload["questions"])
            combined = {k: v for r in single for k, v in r["choices"].items()}
            elapsed = (datetime.fromisoformat(single[-1]["finished_at"])
                       - datetime.fromisoformat(single[0]["started_at"])).total_seconds() * 1000
            measurements.append({
                "repetition": repetition, "full_30_client_ms": full[0]["client_ms"],
                "serial_30_client_sum_ms": sum(r["client_ms"] for r in single),
                "serial_30_wall_ms": elapsed,
                "single_question_ms": timing(r["client_ms"] for r in single),
                "changed_keys": [k for k in combined if combined[k] != full[0]["choices"][k]],
                "full_usage": full[0]["response"].get("usage"),
            })
        groups[provider] = {
            "full_30_ms": timing(m["full_30_client_ms"] for m in measurements),
            "serial_30_wall_ms": timing(m["serial_30_wall_ms"] for m in measurements),
            "single_question_ms": timing(r["client_ms"] for r in group if r["mode"] == "serial_1"),
            "measurements": measurements,
        }
    summary = {
        "case_id": plan["case_id"], "repetitions": plan["repetitions"],
        "formal_http_calls": sum(not r["warmup"] for r in rows), "warmup_http_calls": 3,
        "request_overlap_count": 0, "model_windows_overlap": False,
        "service_start_times_and_restart_counts_unchanged": True,
        "same_full_state_and_candidate_values_verified": True,
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "receipts_sha256": hashlib.sha256((run / "receipts.jsonl").read_bytes()).hexdigest(),
        "models": groups,
    }
    save(run / "summary.json", summary)
    text = [
        "# 空调延迟复核：单任务与逐Key串行", "",
        "使用原测试S03基线的完整业务输入；每个模式预先固定，三个模型依次测试。"
        "每模型先预热一次，每种模式重复3次并交替顺序；无并发HTTP请求，不启停模型。", "",
        "> " + json.loads(payload["state"])["query"], "",
        "- 完整任务：一次请求包含30个Key选择题，等待全部回答后才开始下一任务。",
        "- 逐Key串行：每次只发一个Key的问题，等待返回后再发下一个；30题全部执行。"
        "每次仍携带相同完整30项能力集，不按参考答案过滤问题或候选。",
        "- 下表的单题时间来自实际逐Key请求计时；整任务时间分别按对应执行方式测量。",
        "",
        "| 模型 | 完整30题请求均值 ms | 独立单题均值 ms | 独立单题P95 ms | 逐Key串行完成30题均值 ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for provider, data in groups.items():
        text.append(f"| {LABELS[provider]} | {data['full_30_ms']['mean']:.1f} | "
                    f"{data['single_question_ms']['mean']:.1f} | {data['single_question_ms']['p95']:.1f} | "
                    f"{data['serial_30_wall_ms']['mean']:.1f} |")
    text += [
        "", "完整请求均值每模型3次；单题统计每模型90次，包含不同Key与候选规模。"
        "逐Key整任务耗时包含30次请求及中间记录开销。"
        "这是一道固定Query的延迟诊断，不替代原20题正确率测试，也不是独立同分布的90道测试题。", "",
        "## 拆分后输出是否改变", "",
    ]
    for provider, data in groups.items():
        text.append("- " + LABELS[provider] + "：" + "；".join(
            f"第{m['repetition'] + 1}轮改变{len(m['changed_keys'])}个Key"
            + ("（" + ", ".join(m["changed_keys"]) + "）" if m["changed_keys"] else "")
            for m in data["measurements"]) + "。")
    text += [
        "", "请求state与每题文本一致，不保证服务内部的截断、分批和预处理完全相同；"
        "若输出变化，不能直接用该诊断替换原成绩。", "",
        f"正式调用{summary['formal_http_calls']}次，预热{summary['warmup_http_calls']}次；"
        "全部响应有效。保存的请求时间区间无重叠，三个模型测试区间无重叠。", "",
        "[计划](plan.json) · [完整原始输入](payload.json) · [原始响应](receipts.jsonl) · "
        "[逐次指标](summary.json) · [运行时源码摘录](runtime_sources.json) · "
        "[H2O运行参数](runtime_config.json) · [原实验串行核验](original_serial_audit.json)。",
        "",
    ]
    (run / "LATENCY.zh.md").write_text("\n".join(text))
    print(json.dumps({p: {k: v for k, v in d.items() if k != "measurements"} for p, d in groups.items()},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    analyze(parser.parse_args().run)
