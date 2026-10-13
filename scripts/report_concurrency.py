"""Validate saved load-test evidence and generate a report and exportable charts."""

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from benchmark_concurrency import summarize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("decider", "jev", "bedrock")
NAMES = {"decider": "Strands Decider", "jev": "Jev", "bedrock": "GPT-6.1 Sol"}
COLORS = {"decider": "#009b86", "jev": "#8055a4", "bedrock": "#4566d5"}


def load_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def metric(cell, key, statistic="mean"):
    value = cell[key]
    return f"{value[statistic]:.1f}" if value else "—"


def seconds(cell, key, statistic="mean"):
    return cell[key][statistic] / 1000 if cell[key] else math.nan


def main(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["status"] == "complete"
    corpus = json.loads((folder / "corpus.json").read_text())
    infrastructure = json.loads((folder / "infrastructure-metrics.json").read_text())
    rows = load_lines(folder / "requests.jsonl")
    warms = load_lines(folder / "warmups.jsonl")
    cells = manifest["cells"]
    day = manifest["started_at"][:10]
    count = manifest["design"]["requests_per_cell"]
    repetitions = manifest["design"]["repetitions_per_input_per_cell"]
    levels = "、".join(str(c) for c in manifest["design"]["client_concurrency_levels"])
    deployment = json.loads((folder / "deployment-snapshot.json").read_text())
    api = deployment["api"]
    image = api["containers"][0]["image"]
    for cell in cells:
        selected = [
            r
            for r in rows
            if r["provider"] == cell["provider"] and r["concurrency"] == cell["concurrency"]
        ]
        assert len(selected) == cell["attempts"]
        assert Counter(r["task_index"] for r in selected) == {
            i: manifest["design"]["repetitions_per_input_per_cell"] for i in range(20)
        }
        assert cell["max_observed_inflight"] == cell["concurrency"]
        assert [r["task_index"] for r in sorted(selected, key=lambda r: r["index"])] == corpus[
            "dispatch_order"
        ]
        recalculated = summarize(selected, cell["wall_seconds"])
        for key in recalculated:
            assert recalculated[key] == cell[key], (cell["provider"], cell["concurrency"], key)
        for row in selected:
            if row["success"]:
                task = corpus["tasks"][row["task_index"]]
                assert row["input_verified"] and row["result"]["input_hash"] == task["input_hash"]
    assert sum(c["attempts"] for c in cells) == len(rows)
    assert all(w["success"] for w in warms)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), layout="constrained")
    for provider in PROVIDERS:
        series = sorted(
            (c for c in cells if c["provider"] == provider), key=lambda c: c["concurrency"]
        )
        xs = [c["concurrency"] for c in series]
        ys = [
            [c["successful_requests_per_second"] for c in series],
            [seconds(c, "client_latency_ms_success", "p50") for c in series],
            [seconds(c, "client_latency_ms_success", "p95") for c in series],
        ]
        for ax, values in zip(axes, ys, strict=True):
            ax.plot(xs, values, "o-", color=COLORS[provider], label=NAMES[provider], linewidth=2)
    for ax, title, ylabel in zip(
        axes,
        ("Successful throughput", "Client latency p50", "Client latency p95"),
        (
            "Successful requests / second",
            "Seconds (successful requests)",
            "Seconds (successful requests)",
        ),
        strict=True,
    ):
        ax.set(xscale="log", title=title, xlabel="Concurrent client workers", ylabel=ylabel)
        ax.set_xticks(
            manifest["design"]["client_concurrency_levels"],
            manifest["design"]["client_concurrency_levels"],
        )
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.18)
        ax.legend(frameon=False)
    fig.suptitle(
        f"Payment decision API: {count} requests / model / concurrency level · warm · {day}",
        fontsize=13,
    )
    fig.savefig(folder / "latency-throughput.png", dpi=180)
    fig.savefig(folder / "latency-throughput.svg")
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), sharey=True, layout="constrained")
    for ax, provider in zip(axes, PROVIDERS, strict=True):
        series = sorted(
            (c for c in cells if c["provider"] == provider), key=lambda c: c["concurrency"]
        )
        xs = list(range(len(series)))
        process = [seconds(c, "processing_ms") for c in series]
        waiting = [seconds(c, "backend_wait_and_preamble_ms") for c in series]
        ax.bar(xs, process, color=COLORS[provider], label="Processing (includes upstream/network)")
        ax.bar(xs, waiting, bottom=process, color="#c7cdd5", label="Wait + backend preamble")
        ax.set_xticks(xs, [c["concurrency"] for c in series])
        ax.set(
            title=NAMES[provider], xlabel="Concurrent client workers", ylabel="Mean backend seconds"
        )
        ax.grid(axis="y", alpha=0.18)
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Where backend time accumulates · successful requests only", fontsize=13)
    fig.savefig(folder / "backend-time.png", dpi=180)
    fig.savefig(folder / "backend-time.svg")
    plt.close(fig)

    rel = folder.relative_to(ROOT / "docs").as_posix()
    successful = sum(r["success"] for r in rows)
    cold = sum(c["invocations_with_initialization"] for c in infrastructure["jev_measured_cells"])
    counts_match = all(c["count_matches"] for c in infrastructure["jev_measured_cells"])
    findings = []
    for provider in PROVIDERS:
        series = sorted(
            (c for c in cells if c["provider"] == provider), key=lambda c: c["concurrency"]
        )
        first, last = series[0], series[-1]
        best = max(series, key=lambda c: c["successful_requests_per_second"])
        findings.append(
            f"- **{NAMES[provider]}**：并发 {first['concurrency']} → {last['concurrency']}，"
            f"吞吐 {first['successful_requests_per_second']:.2f} → "
            f"{last['successful_requests_per_second']:.2f} 次/秒；"
            f"p95 {metric(first, 'client_latency_ms_success', 'p95')} → "
            f"{metric(last, 'client_latency_ms_success', 'p95')} ms。"
            f"本轮最高吞吐 {best['successful_requests_per_second']:.2f} 次/秒（并发 {best['concurrency']}）。"
        )
    report = [
        f"# 三模型并发性能测试 · {day}",
        "",
        "测量当前部署的支付决策 API：客户端并发增加时，吞吐、延迟、排队和失败如何变化。"
        "这是完整应用路径的承载测试，保留现有服务并发限制；没有扩容、修改模型权重或执行模拟资金动作。",
        "",
        f"**正式请求 {len(rows)} 次，成功 {successful} 次，失败 {len(rows) - successful} 次；"
        f"另有 {len(warms)} 次预热，不进入正式统计。**",
        "",
        *findings,
        "",
        f"![并发、吞吐与延迟]({rel}/latency-throughput.svg)",
        "",
        "## 测试方法",
        "",
        "- 路径：测试客户端 → CloudFront → ALB → ECS FastAPI → 模型服务。",
        "- 请求单位：一个模型对一个业务步骤进行一次判断；统计的延迟与吞吐都以这个单位计算。",
        f"- 并发档位：{levels}；每档每模型 {count} 次，三个模型分开测试，模型顺序随档位轮换。",
        f"- 输入：四个支付场景 × 五个步骤 = 20 个优化输入，各重复 {repetitions} 次；使用相同的确定性打乱顺序。每次成功响应都验证实际模型输入与指纹。",
        f"- 固定并发施压：每个客户端请求完成后立即补下一个，无思考时间。固定 {count} 次包含起步与末尾排空；每模型单独发压。",
        "- 所有输入先预热；每档还预热 Decider 一个执行槽、Jev/GPT 两个执行槽。暖请求原值另存，正式数据不扣减开销、不挑选较快请求。",
        "- p50/p95 使用 nearest-rank；表中延迟只统计成功请求。原始统计同时保留全请求和失败延迟；吞吐为成功请求数 / 本档实际经过时间。",
        "- HTTP 客户端复用连接，连接池支持最高并发；不自动重试失败请求。后端现有连接重试策略保持原样。",
        "- 只请求决策接口，未执行支付步骤、启停 GPU 或更改生产配置。",
        "",
        f"每档只有 {count} 个混合任务样本，p95 是本轮观测，不报告 P99 或承诺生产 SLA。"
        "未运行持续时间型开放负载、长时间浸泡、突发流量或多租户公平性测试。",
        "",
        "## 部署与并发上限",
        "",
        "| 层级 | 本次配置 |",
        "| --- | --- |",
        f"| 业务后端 | {api['running_count']} 个 ECS Fargate task，{int(api['cpu_units']) / 1024:g} vCPU / {api['memory_mib']} MiB，当前容器入口为 1 个 Uvicorn worker，镜像 {image} |",
        "| Decider | EC2 On-Demand g6.xlarge / NVIDIA L4；业务进程锁与模型服务锁均串行，另有 DynamoDB 独占推理租约 |",
        "| Decider 排队 | 业务进程锁等待超过 5 秒返回 HTTP 429 |",
        "| Jev | 每个 API 进程 2 个调用槽；经 Lambda → HTTPS；总期限 50 秒，包含等待调用槽 |",
        "| GPT | 每个 API 进程 2 个调用槽；Bedrock GPT-6.1 Sol / low；总期限 45 秒，包含等待调用槽 |",
        "",
        "客户端并发 32 不等于 GPU 同时执行 32 次推理。`max_batch=8` 也不表示当前服务支持八个 HTTP 请求同时推理。"
        "这轮结果不能用于宣布某模型或供应商的最大吞吐。",
        "",
        "## 完整结果",
        "",
        "客户端延迟单位 **ms**；吞吐单位 **成功请求/秒**。客户端计时包含认证、HTTP 往返、API 排队及模型处理。"
        "它比 PPT 中的 `backend_total_ms` 多了客户端路径，不能直接混为同一指标。",
        "",
        "| 模型 | 并发 | 成功/尝试 | 吞吐 | 平均延迟 | p50 | p95 | 最大延迟 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for provider in PROVIDERS:
        for c in sorted(
            (c for c in cells if c["provider"] == provider), key=lambda c: c["concurrency"]
        ):
            report.append(
                f"| {NAMES[provider]} | {c['concurrency']} | {c['successes']}/{c['attempts']} | "
                f"{c['successful_requests_per_second']:.2f} | "
                f"{metric(c, 'client_latency_ms_success')} | {metric(c, 'client_latency_ms_success', 'p50')} | "
                f"{metric(c, 'client_latency_ms_success', 'p95')} | {metric(c, 'client_latency_ms_success', 'max')} |"
            )
    report.extend(
        [
            "",
            "## 后端处理与等待",
            "",
            f"![后端耗时分解]({rel}/backend-time.svg)",
            "",
            "`processing_ms` 包含模型调用及通信。`backend_total_ms - processing_ms` 是后端等待和前置处理的近似值；"
            "Decider 还包含取得推理租约的时间，不能全当作纯锁等待。"
            "两项都不是 GPU 纯计算或 Jev 纯推理时间。",
            "",
            "| 模型 | 并发 | 后端总时间均值 ms | processing 均值 ms | 等待及前置均值 ms |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for provider in PROVIDERS:
        for c in sorted(
            (c for c in cells if c["provider"] == provider), key=lambda c: c["concurrency"]
        ):
            report.append(
                f"| {NAMES[provider]} | {c['concurrency']} | {metric(c, 'backend_total_ms')} | "
                f"{metric(c, 'processing_ms')} | {metric(c, 'backend_wait_and_preamble_ms')} |"
            )
    decider_cells = sorted(
        (c for c in cells if c["provider"] == "decider"), key=lambda c: c["concurrency"]
    )
    first, last = decider_cells[0], decider_cells[-1]
    report.extend(
        [
            "",
            f"Decider 从并发 {first['concurrency']} 到 {last['concurrency']}，"
            f"模型服务自报平均耗时为 {metric(first, 'model_reported_ms')} → "
            f"{metric(last, 'model_reported_ms')} ms；后端等待及前置处理则为 "
            f"{metric(first, 'backend_wait_and_preamble_ms')} → "
            f"{metric(last, 'backend_wait_and_preamble_ms')} ms。"
            "模型服务自报时间也不是单独的 GPU kernel 时间。",
        ]
    )
    report.extend(
        [
            "",
            "## 调用失败与选择结果",
            "",
            "| 模型 | 成功/尝试 | HTTP 状态 | 与演示参考一致/成功 |",
            "| --- | ---: | --- | ---: |",
        ]
    )
    for provider in PROVIDERS:
        selected = [r for r in rows if r["provider"] == provider]
        success = [r for r in selected if r["success"]]
        counts = dict(Counter(str(r["status"]) for r in selected))
        matches = sum(r["result"]["matches_reference"] for r in success)
        report.append(
            f"| {NAMES[provider]} | {len(success)}/{len(selected)} | {counts} | {matches}/{len(success)} |"
        )
    report.extend(
        [
            "",
            "重复请求用于观测性能与输出变化，不能把同一 20 个任务的重复次数当成更多独立业务评测样本；"
            "参考一致仍不等于通用准确率。本次没有执行业务流程，不能据此统计资金完成率。",
            "",
            "## Lambda 与 ECS 观测",
            "",
            f"Jev 各档 Lambda START/REPORT 数量与请求数{'全部一致' if counts_match else '未全部一致，需要核查'}；"
            f"正式测量窗口内有 **{cold} 次**包含初始化记录。",
            "",
            "日志按每档测试的开始/结束时间归组；并发请求未逐条关联，因为应用不返回 Lambda RequestId。"
            "这只能观察本项目代理环境，不能证明上游 Jev 没有冷启动，也无法分离其纯推理时间。",
            "",
            "ECS CPU / 内存按 60 秒采样，原始值随证据保存；相邻模型及预热可能落入同一个采样点。"
            "CloudWatch 数据可能延迟到达，最新采样时间和测试结束分钟单独记录。"
            "没有 GPU 利用率样本，因此不根据应用排队推断 GPU 利用率或模型极限。",
            "",
            "## 如何使用结论",
            "",
            "本次配置中，Decider 受串行执行与独占租约约束；Jev/GPT 受两调用槽约束。"
            "高客户端并发主要让请求等待，是否增加吞吐要看表中实际值。"
            "继续优化时，应分别评估 API CPU、认证/租约开销、上游调用槽、模型批处理和副本数，重新测试后再调整容量。",
            "",
            "不要直接移除 Decider 锁：当前推理引擎含可变状态。需要先验证受支持的批处理或多实例方案。"
            "提高 Jev/GPT 调用槽也须重测供应商限额、后端资源和超时行为，当前未部署这些改动。",
            "",
            "## 原始证据与复现",
            "",
            f"- [测试配置、各档统计]({rel}/manifest.json)",
            f"- [逐请求输入索引、输出、计时和错误]({rel}/requests.jsonl)",
            f"- [20 个输入与发起顺序]({rel}/corpus.json) · [预热记录]({rel}/warmups.jsonl)",
            f"- [实际部署快照]({rel}/deployment-snapshot.json) · [Lambda / ECS 日志指标]({rel}/infrastructure-metrics.json)",
            f"- [数据验证]({rel}/verification.json)",
            "",
            "```bash",
            "# 会调用真实模型；输出目录必须是新的目录，凭据不会写入结果。",
            "uv run python scripts/benchmark_concurrency.py \\",
            "  --credentials .deployment/admin-credentials.json \\",
            "  --output docs/results/concurrency-NEW-DATE",
            "",
            "uv run python scripts/collect_concurrency_metrics.py docs/results/concurrency-NEW-DATE",
            "uv run --with matplotlib python scripts/report_concurrency.py docs/results/concurrency-NEW-DATE",
            "```",
            "",
        ]
    )
    (ROOT / "docs/CONCURRENCY.md").write_text("\n".join(report))
    verification = {
        "verified_at": datetime.now(UTC).isoformat(),
        "measured_calls": len(rows),
        "warmup_calls": len(warms),
        "cells": len(cells),
        "balanced_corpus_all_cells": True,
        "dispatch_order_identical_all_cells": True,
        "all_successful_inputs_match_corpus": True,
        "all_statistics_recomputed_from_rows": True,
        "max_inflight_matches_requested_all_cells": True,
        "files_sha256": {
            name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
            for name in (
                "manifest.json",
                "corpus.json",
                "requests.jsonl",
                "warmups.jsonl",
                "deployment-snapshot.json",
                "infrastructure-metrics.json",
            )
        },
        "source_files_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_concurrency.py",
                "app/main.py",
                "app/crypto.py",
                "app/gpu_state.py",
                "deployment/model_server.py",
                "deployment/api.Dockerfile",
            )
        },
    }
    (folder / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        f"Validated {len(rows)} measured calls; generated docs/CONCURRENCY.md and PNG/SVG charts."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    main(parser.parse_args().folder.resolve())
