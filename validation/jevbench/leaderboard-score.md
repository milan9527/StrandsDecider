# JevBench 榜单分数复算

2026-10-16 核对 [开源模型榜](https://benchmarkheaven.com/jev-models)、[API 榜](https://benchmarkheaven.com/jev-models/api)及其当前公开方法 v1.6.1。

**本次 Strands Decider 的 72.73% 是旧版 231 道公开题的正确率，现有数据不足以计算正式榜单总分或名次。** 可以计算的速度和成本分项如下；这些是本地估算，不是 Benchmark Heaven 发布的 Strands 成绩。

| 项目 | 结果 | 口径 |
|---|---:|---|
| 公开题正确率 | **72.73%** | 168/231，JevBench v1 |
| Intelligence 智能分 | **暂无** | 不能用原始正确率替代 |
| Calibration 校准分 | **暂无** | 不能用 `100 × (1 − ECE)` 替代 |
| Speed 速度分估算 | **85.62** | 将本次私网 P50/P95 代入自托管 `2×耗时+150 ms` 假设 |
| Cost 成本分估算 | **56.52** | g6.xlarge 按需价、单并发、平均请求耗时、100% 请求时间占比 |
| Capability 能力分 | **暂无** | 缺少 Intelligence、Calibration |
| Composite 综合分 / 名次 | **暂无** | 缺少完整评测；不能把两个估算分项拼成正式成绩 |

数据：[计算结果](runs/2026-10-16-original/leaderboard-score.json) · [榜单聚合数字快照](runs/2026-10-16-original/leaderboard-reference.json) · [EC2 价格核验](runs/2026-10-16-original/ec2-price-reference.json) · [本次测试详情](README.md)

## 两个榜单的区别

开源榜主要按 **Capability = (Intelligence + Calibration) / 2** 排序，同时要求满足 Jev-class 的延迟和成本门槛。API 榜主要按 **Composite** 排序，将质量、校准、速度、成本一起考虑。

当前主发布集为 **300 道公开题 + 1,200 道封闭题**。一些后续 API 行使用另行标注、经过等值校正的子集。本次旧版 231 题不能视为已经覆盖新版 300 题，也没有封闭题成绩。

Intelligence 包含随机猜测校正、题型和难度权重、公开与封闭集各 50% 的组合，以及公开/封闭集差距惩罚。Choice、Noul、Score 等权；简单、标准、困难、评判的权重分别为 10%、20%、40%、30%。Calibration 使用概率分布，包含不同题型的校准与分布误差。本次保存的 ECE 0.0499 和 Brier 0.3483 有参考价值，但不足以替代该分项。

## 公式与已发布成绩核验

令 `I`、`C`、`S`、`K` 分别表示 Intelligence、Calibration、Speed、Cost，均为 0–100 分。默认 Option A：

```text
H = 4 / (1/I + 1/C + 1/S + 1/K)
Composite = H × min(1,I/50)² × min(1,S/50)² × min(1,K/50)²
```

任一分项为零，总分为零；缺少分项则没有总分。这里使用调和平均，低于 50 的智能、速度或成本分还会触发平方惩罚。

以官方发布的轴值复算：

| 模型 | 智能 I | 校准 C | 速度 S | 成本 K | 能力分 | 综合分 |
|---|---:|---:|---:|---:|---:|---:|
| Sage 1.3.0 | 65.59 | 91.60 | 93.62 | 58.23 | 78.60 | **74.05** |
| Jev 1.13.0 | 63.62 | 90.63 | 91.50 | 54.73 | 77.13 | **71.49** |
| H2O-Lightning-4B v1.1 | 60.04 | 89.95 | 92.61 | 60.30 | 75.00 | **72.52** |

这些是 Benchmark Heaven 发布的数据，**不是本项目重新运行这三个模型的结果**。已核验 v1.6.1 聚合文件中全部 137 个可用综合分、140 个速度分、137 个成本分和 140 个能力分；最大差异仅为浮点舍入的 `1.42e-14`。

本次抓取的两个榜单未找到 `Strands Decider / Hobson` 条目。榜单上的 Mapika `decider-2b` 等同名模型不是本项目的 Strands Decider，不能借用其得分或名次。

## 本次速度怎样折算

榜单对 P50 和 P95 分别打分，再取平均：

```text
speed_point(t) = clip(100 − 20 × log10(t / 0.1秒), 0, 100)
Speed = (speed_point(P50) + speed_point(P95)) / 2
```

| 代入方式 | P50 | P95 | 速度分 |
|---|---:|---:|---:|
| 本次私网客户端实测直接代入 | 68.32 ms | 403.71 ms | 93.94 |
| 套用自托管榜单的 `2×耗时+150 ms` 假设 | 286.65 ms | 957.42 ms | **85.62** |

官方自托管测量从 GPU 主机回环调用，因此增加网络估算；本次是 Fargate 经私网 HTTP 调用，已经包含少量网络耗时。第二行只是套用同一公式的敏感性估算。第一行也不是官方测量端访问公网 API 的结果，两者都不能直接与 API 榜的实测分项作公平排名。

## 本次成本怎样折算

2026-10-16 通过 AWS Price List API 核验：us-east-1、Linux、Shared、g6.xlarge 按需价格为 **$0.8048/小时**。仅 EC2 计算费，730 小时为 **$587.50**；磁盘、网络、业务服务和测试客户端另计。

榜单成本轴的公式为：

```text
Cost = clip(100 − 30 × log10(每千次美元成本 / 0.001), 0, 100)
```

网站另有 GPU **What-If 成本计算器**，按 `3600 / P50` 估计每小时决策数；此计算器不改变正式榜单成绩。对本次单并发数据：

| 成本假设 | 每千次成本 | 成本分 |
|---|---:|---:|
| 网站 What-If：按 P50，100% 时间有请求 | $0.01527 | 64.48 |
| 按平均耗时 125.91 ms，100% 时间有请求 | **$0.02815** | **56.52** |
| 按平均耗时，50% 时间有请求 | $0.05629 | 47.49 |
| 按平均耗时，10% 时间有请求 | $0.28147 | 26.52 |

平均耗时口径的算式是 `0.8048 × 0.125906592 × 1000 / 3600 / 请求时间占比`。这里的“时间有请求”是请求服务时间占比，不是 NVIDIA 报告的 GPU 利用率。满负荷假设也不代表测得了持续吞吐；100% 一行未计真实请求间隙与空闲开销，后两行展示请求时间占比下降时的成本。

这一批有少量较慢请求，P50 明显低于平均值，因此按 P50 估计成本更乐观。正式榜单的成本来自其规定的价格与共同题集口径，不能由上述 EC2 What-If 自动替代。也不能拿测试账本的零 token 费用计算出 100 分。

## 获得正式可比成绩还缺什么

需要通过榜单维护方的评测流程，在冻结版本、同一题集和成本口径下运行模型端点，覆盖当前公开集及封闭集，再执行版本对应的评分和重采样。封闭题及逐题预测不公开下载；仅重新运行本地 231 题无法补齐。

目前可以据实报告：**Strands Decider 在旧版公开集答对 72.73%，私网 P50 为 68.3 ms；按榜单公式可计算速度与成本的条件估算，但正式能力分、综合分和排名待完整评测。**

## 复算

以下命令只读取仓库中的聚合数据，不调用模型：

```bash
python scripts/calculate_jevbench_board_scores.py \
  --output /tmp/decider-jevbench-board-score.json
```

脚本先复算已发布分数，再输出本次分项估算；缺失的智能分、校准分、综合分和名次保留为 `null`。参数 `--hourly-usd` 可用于成本敏感性计算。

来源：

- [JevBench 方法说明](https://benchmarkheaven.com/jev-models/methodology)
- [v1.6.1 聚合发布文件](https://benchmarkheaven.com/api/jevbench/v1.6.1)，本次内容 SHA-256：`5cd8c1332226ea9c179883d2285c0d8b8cc593ae38f2645197364a7ddd9c83c1`
- [综合分公式源码](https://github.com/fstandhartinger/model-market-comparison/blob/e4b777b10a18b185f0174be3ad14a570cc8abcd3/lib/jevbench-axis-weights.mjs)
- [速度与成本换算源码](https://github.com/fstandhartinger/model-market-comparison/blob/e4b777b10a18b185f0174be3ad14a570cc8abcd3/lib/jevbench-v12-score.mjs)，文件中的历史 Intelligence/几何平均公式不用于本次 v1.6.1 总分
- [GPU What-If 成本计算器源码](https://github.com/fstandhartinger/model-market-comparison/blob/e4b777b10a18b185f0174be3ad14a570cc8abcd3/lib/jevbench-gpu-cost.mjs)
