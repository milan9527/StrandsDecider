# Strands Decider × Jev × GPT · v10 · 32 页

基于 v9 的 52 页重排：保留模型原理、三模型支付与路由实测、真实截图和 vLLM 性能；增加 `validation/` 场景验证，以及 EC2 Standard Reserved Instances（RI）成本。合并重复的场景截图、方法解释和选型结论，原 v9 文件保留。

- **[PPTX](Strands-Decider-v10-场景验证-vLLM与RI成本对比-32页-20261015.pptx)** · [PDF](Strands-Decider-v10-场景验证-vLLM与RI成本对比-32页-20261015.pdf)
- [全套预览](slides-overview.png) · [场景验证预览](validation-overview.png) · [成本预览](cost-overview.png)
- [逐页讲稿与来源](讲稿与来源.md) · [数据与图片清单](build-manifest.json) · [渲染和成本核验](render-audit.json)

## 故事线

| 页码 | 内容 |
| --- | --- |
| 1–5 | 业务中的高频判断 → Decider 原理 → BERT / Jev / GPT → JevBench |
| 6–10 | AWS 架构 → 四场景支付结果 → 退款截图 → 一次完整业务闭环 |
| 11–13 | 两步模型路由实现 → 三模型结果 → 中英文索引截图与证据差异 |
| **14–20** | **新增场景验证**：Skills、真实浏览器、金融、政策路由，以及独立项目的游戏记录 |
| 21–22 | 实测输入优化 14/20 → 18/20；后续回归、确定性检查与微调路线 |
| 23–27 | vLLM 适配和部署 → 原版对照 → 并发与 token 预算 → Jev 并发对比 |
| **28–30** | **加入 RI**：六种 Standard RI 付款方式、与 Jev 的费用交点、运行时长与期限承诺 |
| 31–32 | 基于实际结果的选型结论；Demo、仓库、验证报告和评测链接 |

JevBench 原三页合并为一页；支付保留总表、一个关键截图和一个闭环；主应用路由保留实现、总表和检索证据；微调与优化建议合并；并发和 batch 预算共用一页；选型结论只出现一次。逐页与 v9 的对应关系见构建清单。

## 场景验证

来源为已经发布的 [validation 汇总](../../../validation/README.md)及其原始记录。实验日期为 2026-10-12—13，本次没有重新调用模型。

| 实验 | 评分单位 | Decider | Jev |
| --- | --- | ---: | ---: |
| Skills | 65 个可判定问题 | 50/65 | 65/65 |
| 真实浏览器 | 5 个任务，各运行 2 次 | 4/10 完成 | 10/10 完成 |
| 金融业务 | 30 题，原始候选顺序 | 22/30 | 28/30 |
| 政策路由 | 32 题，两种候选顺序 | 25/64 | 46/64 |
| 政策路由：自然语言对照 | 24 道复合政策题，两种顺序 | 8/48 | 31/48 |
| 俄罗斯方块：数字字段 | seed 42，每局最多 50 块 | 36 块 / 0 行 | 50 块 / 19 行 |
| 俄罗斯方块：自然语言 | 同一种子与上限 | 43 块 / 2 行 | 50 块 / 19 行 |

Skills 64 次、浏览器和金融 178 次、两批政策路由 224 次，共 **466 次有效返回**。游戏是独立项目的已有记录，不计入 466 次。问题、请求和任务不能相加计算总准确率，顺序反转也不增加独立业务案例。

第 17 页并排展示真实银行查询终点：Decider 在入口页结束；Jev 返回 JPMorgan Chase Bank 查询结果，FDIC Cert 628。截图只裁切可读区域，原图、裁切坐标及哈希保留。浏览器采用修订后的 10/10 Jev 完成数：原检查器漏匹配官方页面的 `60 calendar days`，按保存页面更正，原评分和修订记录均保留，没有模型重跑。

金融验证保留两模型共同错误：同一人、同一家银行、同一所有权类别的 18 万与 12 万美元需合并，两者均误判全部受保。政策路由则显示“语义分类较好”不能推广为“满足所有预算、能力和可用性约束”。

这轮验证使用 **Decider v19 原版服务和 Jev 1.13.0**，没有 GPT，也没有 vLLM。它与网页四任务、三模型的路由实验是不同实验。

| 独立验证的客户端 RTT 中位数 / P95 | Decider | Jev |
| --- | ---: | ---: |
| Skills | 164.6 / 911.1 ms | 119.9 / 163.8 ms |
| 浏览器＋金融 | 99.8 / 303.7 ms | 139.4 / 182.3 ms |
| 政策路由首轮 | 211.4 / 219.2 ms | 137.4 / 173.1 ms |
| 路由自然语言 | 219.2 / 298.2 ms | 132.7 / 193.1 ms |

Skills 一次请求包含 1–6 个问题，没有正式预热阶段；Decider 首次六问题请求 13.511 秒原样保留，原因未确定。浏览器两侧路径和请求数不同，不能把过早结束视为性能优势。这些独立验证中 Jev 直连 API；支付批次经 Lambda，时延不做跨批次合并。

## RI 与 Jev：价格和计算

**2026-10-15** 查询 AWS Price List，固定 `us-east-1 / Linux / Shared / g6.2xlarge`，比较 On-Demand 和 Standard RI，不混入 Convertible RI 或 Savings Plans。

| 购买方式 | 一次预付 | 后续小时费 | 折算月计算费 | 相对按需节省 |
| --- | ---: | ---: | ---: | ---: |
| 按需 | $0 | $0.97760 | $713.65 | — |
| 1 年无预付 | $0 | $0.63642 | $464.59 | 34.9% |
| 1 年部分预付 | $2,655 | $0.30306 | $442.48 | 38.0% |
| 1 年全预付 | $5,203 | $0 | $433.58 | 39.2% |
| 3 年无预付 | $0 | $0.44872 | $327.57 | 54.1% |
| 3 年部分预付 | $5,459 | $0.20774 | $303.29 | 57.5% |
| 3 年全预付 | $10,264 | $0 | $285.11 | 60.0% |

按 AWS 的一年 365 天、三年 1095 天，使用年均 730 小时/月：

```text
折算月费 = 预付额 / (12 × 年数) + 后续小时费 × 730
Jev 费用 = 实际输入 token × $0.042 / 1,000,000
月调用交点 = EC2 折算月计算费 / Jev 单次费用
```

Jev 公开单价为 **$0.042 / 百万输入 token，输出免费**。支付压测实际 10,240 次请求共 6,727,168 输入 token，平均 656.95，约 **$27.5919 / 百万次决策**；四任务两步路由平均 2,805.75 token，约 **$117.8415 / 百万条完整路由**。

| 计算费方案 | 支付单次费用交点 / 月 | 完整两步路由费用交点 / 月 |
| --- | ---: | ---: |
| 按需 | 2,586 万次 | 606 万条 |
| 1 年无预付 RI | 1,684 万次 | 394 万条 |
| 1 年全预付 RI | 1,571 万次 | 368 万条 |
| 3 年全预付 RI | 1,033 万次 | 242 万条 |

**折算月费不是每月实际账单。** 全预付在开始时支付；无预付、部分预付也承诺整个期限，停止实例仍付费。区域 RI 为匹配用量提供计费优惠，不预留容量。本次只查询价格，没有购买 RI。

若按需实例可随业务停机，1 年无预付、1 年全预付、3 年全预付 RI 相对按需的运行时长交点分别约为期限的 **65.1%、60.8%、40.0%**。这是开机时长占比，不是 GPU 利用率。

以上为计算费和 Jev 调用费估算，未计 EBS、网络、业务应用、运维、冗余、税和下游目标模型执行。`g6.2xlarge` 是指定的成本场景，本批性能在 `g6.xlarge` 或标明的同机对照配置上测量，不能作为 `g6.2xlarge` 的容量保证；也不是当前两台 `g6.xlarge` 的合计账单。

- [AWS 原始价格响应](sources/aws-g6.2xlarge-pricing.json) · [逐项公式与交点](sources/cost-calculation.json)
- [AWS RI 付款与期限](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-reserved-instances.html) · [区域 / 可用区范围](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/reserved-instances-scope.html)
- [Jev 官方价格](https://typesafe.ai/blog/introducing-system-one-models-and-jev) · [抓取来源](sources/web-source-manifest.json)

## 构建与核验

```bash
uv run --no-project --with python-pptx --with pillow --with cairosvg \
  --with matplotlib python scripts/build_presentation_v10.py

# 使用 LibreOffice 将 PPTX 导出为同目录 PDF，然后执行：
uv run --no-project --with python-pptx --with pillow --with pymupdf \
  python scripts/verify_presentation_v10.py
```

文字、表格、流程和架构均可编辑，采用现有 AWS 官方服务图标和 Lucide 图标；原始截图及科学图表以图片嵌入。检查覆盖 32 页、正文渲染、图形边界、逐页讲稿、来源与截图哈希、v9 文件不变、六种 RI 原价和全部费用交点。另行目视检查截图、对照表和架构页。

Demo：<https://d3i7ogfx5ml7dc.cloudfront.net>

主项目：<https://github.com/milan9527/StrandsDecider>

vLLM 项目：<https://github.com/milan9527/StrandsDeciderVLLM>
