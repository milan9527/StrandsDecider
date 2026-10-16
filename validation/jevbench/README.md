# Strands Decider · JevBench 公开集实测

2026-10-16 在当前演示的 **原版 Strands Decider v19、us-east-1、g6.xlarge / NVIDIA L4** 上，使用官方固定版本运行 231 道公开题。结果为 **168/231，正确率 72.73%**，调用失败与格式错误均为 0。

[官方汇总 JSON](runs/2026-10-16-original/summary.json) · [分层统计与历史结果对照](runs/2026-10-16-original/analysis.json) · [证据核验](runs/2026-10-16-original/verification.json)

[榜单公式复算与分项估算](leaderboard-score.md)：核验已发布的 137 个综合分；本次速度按自托管假设折算为 85.62，EC2 满负荷按平均请求耗时分摊的成本分为 56.52。缺少当前题集与封闭集，正式能力分、综合分和排名暂无。

## 测试方法

- JevBench 提交固定为 `1bcc55eb6c8cffde2306b3db03ede39b61c6152a`。题集为 `original.jsonl` 72 题、`easy.jsonl` 48 题、`hard.jsonl` 111 题；程序、评分器、题目和候选顺序未修改。
- `typesafe` 适配器直接调用原版模型的 `/v1/systemone`。每次一道题，单并发，不重试，不通过支付工作台或模型路由业务接口。
- 先分别预热 Choice、Noul、Score 各一次；三次预热独立保存，不计入正式 231 题。
- 正式阶段为 **02:46:00–02:46:32 UTC**。模型窗口 4096 tokens，实际输入 82–3936 tokens，平均 661.1 tokens。
- 测试客户端是临时 ECS Fargate 任务，通过私网 HTTP 连接已经运行的 GPU。模型没有重新启动、换权重或改推理配置。
- 保存每道题的实际请求、响应、概率、评分、耗时和原始响应哈希。核验所有请求均与官方适配器构造的输入一致，并以原始概率重新计算全部 231 题的分数和汇总。

这是 **JevBench v1 的 231 题公开子集**，不是现有榜单的 1,500 题或 600 题发布评测，也不产生榜单 Composite 综合分。本次测试对象为原版 Decider；不混入 vLLM、Jev 或 GPT 的结果。

## 总体结果

| 指标 | 本次结果 |
|---|---:|
| 完成请求 | 231/231 |
| 答对 / 答错 | 168 / 63 |
| 正确率 | 72.73% |
| 调用失败 | 0 |
| 严格响应格式有效性 | 100% |
| Brier | 0.3483 |
| ECE | 0.0499 |
| 客户端平均延迟 | 125.9 ms |
| 客户端 P50 / P95 | 68.3 / 403.7 ms |
| 服务端报告 P50 / P95 | 66.3 / 400.9 ms |
| 成对改写预测一致 | 31/36，86.11% |
| 成对改写两题都正确 | 30/36，83.33% |

Brier 和 ECE 越低越好。本版本 Brier 对完整类别概率分布计算平方误差和；ECE 使用最高标签概率、10 个等宽区间。两者不是接口 `confidence` 字段的直接平均。

客户端延迟包括私网往返、服务排队与模型处理；服务端报告值由模型评估路径计时，不能直接称为纯 CUDA kernel 时间。本表是一次完整题集的观测，不是并发压力测试或生产 P95 保证。成本未计入本次质量评分；测试账本的 `$0.0000` 表示没有按 token 计费记录，不代表 EC2 和临时 Fargate 免费。

## 按难度

| 难度 | 答对 / 题数 | 正确率 | 客户端 P50 | 客户端 P95 |
|---|---:|---:|---:|---:|
| 简单 | 48/48 | 100.00% | 68.4 ms | 70.0 ms |
| 标准 | 65/72 | 90.28% | 66.5 ms | 68.2 ms |
| 困难 | 55/111 | 49.55% | 74.5 ms | 505.3 ms |

## 按任务类型

| 任务族 | 答对 / 题数 | 正确率 |
|---|---:|---:|
| 信息抽取 `extraction` | 24/24 | 100.00% |
| 事实判断 `fact` | 12/12 | 100.00% |
| 意图识别 `intent` | 23/24 | 95.83% |
| 顺序等级 `ordinal` | 12/12 | 100.00% |
| 工具选择 `tool_selection` | 12/12 | 100.00% |
| 路由 `routing` | 11/12 | 91.67% |
| 困难路由 `routing_hard` | 5/5 | 100.00% |
| 规则判断 `policy` | 9/12 | 75.00% |
| 充分性判断 `adequacy` | 10/12 | 83.33% |
| 歧义判断 `ambiguous` | 5/7 | 71.43% |
| 对抗输入 `adversarial` | 3/6 | 50.00% |
| 困难评判 `judge_hard` | 10/17 | 58.82% |
| 长规则 `long_policy` | 7/19 | 36.84% |
| 多跳推理 `multi_hop` | 8/18 | 44.44% |
| 概率判断 `probability` | 3/10 | 30.00% |
| 时序与数值 `temporal_numeric` | 3/15 | 20.00% |
| 权衡选择 `tradeoff` | 4/6 | 66.67% |
| 陷阱题 `trap` | 7/8 | 87.50% |

本批结果支持优先评估 Decider 的意图分类、信息抽取、工具选择和短路由判断。长规则、时序数值及多跳推理仍是主要短板。

`routing_hard` 只有五题，题型也不等于本项目按多项评测数据选择具体模型。因此这里 5/5 不能推翻业务模型路由中的误选。本次保留题目原始排列，没有增加选项换序实验；成对改写一致性也不等于选项顺序稳定性。

## 与模型包历史报告的区别

同一 v19 模型包随附的 `eval/jevbench-w4096/results.jsonl` 报告 167/231。本次逐题比较：

- 230/231 题预测相同。
- 一道 `judge_hard` 真/假判断从错误变为正确，没有正确变错误的题。
- 该题的成立概率从 **0.4973** 变为 **0.5007**，恰好跨过 0.5 阈值。

这不是输入优化或微调收益。权重与题目未改；目前只能确认阈值附近的小幅概率变化，未进一步隔离其运行数值差异来源。历史报告的时间与本次测试的网络、硬件测量口径不同，不据此宣称性能提升。

## 原始记录与资源清理

本地完整记录保存在忽略目录：

```text
.deployment/jevbench-20261016T024524Z-original/
  results.zip
  results/
    tasks.jsonl
    results.jsonl
    raw/
    warmups.json
    summary.json
    manifest.json
    run-meta.json
    health-before.json
    health-after.json
  aws-job.json
  ecs-task-final.json
  cloudwatch.json
  cleanup.json
```

本目录只发布聚合结果与证据哈希。完整逐题文本、响应和 AWS 运行记录在本地保留。

临时 ECS 测试任务已以退出码 0 停止，其任务定义已注销，私有 S3 的两份临时文件已删除。原版 GPU EC2 与原模型任务保持运行；本次未启停 GPU。

## 复现

在能直接访问原版模型 HTTP 服务的机器上运行，结果目录必须位于 JevBench checkout 之外且为空：

```bash
git clone https://github.com/fstandhartinger/jevbench.git /tmp/decider-jevbench
git -C /tmp/decider-jevbench checkout 1bcc55eb6c8cffde2306b3db03ede39b61c6152a

python scripts/run_jevbench_endpoint.py \
  --harness /tmp/decider-jevbench \
  --endpoint http://127.0.0.1:8099 \
  --output /tmp/decider-jevbench-results-new
```

脚本校验 v19 身份和 4096 窗口，不启动模型。当前保存运行的核验命令为：

```bash
uv run python scripts/analyze_jevbench_run.py \
  --harness .deployment/jevbench-tooling \
  --run .deployment/jevbench-20261016T024524Z-original/results \
  --output /tmp/decider-jevbench-audit-new \
  --reference .deployment/models/decider/eval/jevbench-w4096/results.jsonl
```

核验只读取已保存数据，不重新调用模型。

参考：[JevBench 固定版本](https://github.com/fstandhartinger/jevbench/tree/1bcc55eb6c8cffde2306b3db03ede39b61c6152a) · [Strands 官方复现说明](https://github.com/strands-labs/strands-decider/blob/63d24ae286e50105fba0bd1db15b0e243aea4650/evaluation/jevbench.md)
