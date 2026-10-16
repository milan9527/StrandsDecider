# Strands Decider × Jev × GPT · v9 · 52 页

基于 v8 保留原有模型原理、JevBench、支付实测与优化内容，补入决策模型适用场景、模型路由、vLLM 部署与并发性能、g6.2xlarge 与 Jev 成本。原 v8 文件不变；新版保留其 30 页，新增 22 页。

- **[PPTX](Strands-Decider-模型原理与业务演示-v9-适用场景-模型路由-vLLM与成本对比-52页-20261013.pptx)** · [PDF](Strands-Decider-模型原理与业务演示-v9-适用场景-模型路由-vLLM与成本对比-52页-20261013.pdf)
- [全套预览](slides-overview.png) · [新增页面预览](new-slides-overview.png) · [逐页讲稿与来源](讲稿与来源.md)
- [构建与来源记录](build-manifest.json) · [渲染检查](render-audit.json) · [保留的 v8](../v8/README.md)

## 故事线

| 页码 | 内容 |
| --- | --- |
| 1–7 | 保留模型原理、三模型调用方式和 BERT 对比 |
| **8–9** | **新增适用场景**：客服、支付风控、工具与模型路由、RAG、内容审核、告警与线索；适用条件与业务执行边界 |
| 10–25 | 保留 JevBench、AWS 架构、支付过程与截图、性能、行为差异和闭环 |
| **26–32** | **新增模型路由**：两步决策实现、四场景输入与结果、真实截图、错误分析与结论 |
| 33–36 | 保留输入优化、最小对照与微调方案 |
| **37–45** | **新增 vLLM**：适配原理、部署流程、AWS API 架构、测试方法、原版对照、1–128 并发、批次预算与 Jev 对比 |
| **46–48** | **新增成本**：公开价格、实测 token、月用量与交点、支付单步和两步路由的差别 |
| 49–52 | 应用建议、支付结果回顾、综合结论、Demo / Repo / vLLM 地址 |

原 v8 的 27 页正文文字和图片经程序检查保持一致，仅更新页脚编号；封面、支付总结标题和链接页做必要更新。适用场景是应用方向和工作台示例，不宣称所有场景均完成质量实测。

## 模型路由：原始选择与实际截图

采用 2026-10-13 完整复测：4 场景 × 3 决策器 × 2 步，共 24 次有效返回，6 次预热另存。原始输入、输入指纹、每步响应与计时见[路由记录](../../results/workflow-routing-2026-10-13/results.json)，详细解释见[独立报告](../../MODEL_ROUTING_COMPARISON.md)。

| 场景 | Decider：目标 / 两步耗时 | Jev：目标 / 两步耗时 | GPT-6 Sol low：目标 / 两步耗时 |
| --- | --- | --- | --- |
| 客服 | Opus 5 / 461.0 ms | Opus 5.5 / 747.9 ms | GPT-6 Luna / 1464.8 ms |
| 代码 | Opus 5 / 522.6 ms | Sonnet 5.5 / 933.3 ms | Sonnet 5.5 / 6168.2 ms |
| 分析 | Opus 5 / 504.6 ms | Opus 5.5 / 820.4 ms | GPT-6.1 Sol / 12106.1 ms |
| 索引 | Embed English / 182.2 ms | Embed Multilingual / 801.7 ms | Embed Multilingual / 1900.8 ms |

三者均选对流程；Decider 的中英文索引选型不合适，代码选型较缺乏本批代码评测依据。客服与分析未执行目标任务，不能只按型号判优劣。完整复测的有效返回不等于全部选对；首轮 GPT 分析场景的 40 秒超时保留，不混入复测统计。

第 29–31 页使用现有真实页面截图裁剪，包含四个场景；没有重绘或替换截图内的型号、输入输出或耗时。原始图片、裁剪边界与 SHA-256 记录在构建清单中。路由仍调用官方原版 Decider，未切换至 vLLM。

## vLLM：各批次保持各自测量条件

| 批次 | 硬件与路径 | 本版使用的主要数据 |
| --- | --- | --- |
| 原版 vs vLLM | 同一 g6.4xlarge / L4，推理容器限 4 vCPU / 14 GiB，回环 HTTP | 8 并发吞吐 14.76 → 34.91 次/秒，P95 542.8 → 237.6 ms；展示完整复测，历史另有五次超时 |
| vLLM 1–128 | g6.xlarge / L4，CloudFront HTTPS | 每档 1280 次；8 并发 33.84 次/秒，128 并发 P95 4986.1 ms；含复测共 12800 次成功，一次数值偏差超阈值 |
| 批次 token 预算 | 同一 g6.xlarge，仅改变 8192 / 16384 / 32768 预算 | 含复测共 23040 次成功，未获得持续吞吐提升 |
| vLLM vs Jev | g6.xlarge 公网 API vs Jev 直连；相同客户端和业务输入 | 正式成功 10239/10240 vs 10240/10240；vLLM 单并发更低延迟，Jev 8–32 并发更高吞吐，高并发两侧尾延迟增加 |

Jev 对比使用单步骤支付语料，不是模型路由的较长输入。20 条输入重复用于性能测试，不是数千个独立准确率样本。vLLM 改善调度和推理性能，没有训练模型或修正业务选择。

从独立仓库复制的[性能证据与来源清单](sources/vllm/provenance.json)包含固定提交链接及文件哈希；[摘要](sources/vllm/jev-summary.json)保留 HTTP 失败与数值偏差，逐请求大文件通过原仓库链接访问。

- [vLLM 项目](https://github.com/milan9527/StrandsDeciderVLLM)
- [适配过程](https://github.com/milan9527/StrandsDeciderVLLM/blob/main/docs/ADAPTER.zh-CN.md)
- [并发与批次报告](https://github.com/milan9527/StrandsDeciderVLLM/blob/main/docs/VLLM_PERFORMANCE.zh-CN.md)
- [Jev 对比报告](https://github.com/milan9527/StrandsDeciderVLLM/blob/main/docs/JEV_CONCURRENCY.zh-CN.md)

## 成本：公开价格 × 实测用量

2026-10-13 查询 AWS Price List API，并读取 Jev 官方价格页面：

| 项目 | 数据 |
| --- | ---: |
| us-east-1 Linux g6.2xlarge 按需计算费 | $0.9776 / 小时 |
| 730 小时计算费 | $713.648 / 月 |
| 160 GB gp3，$0.08 / GB 月 | $12.80 / 月 |
| 计算 + 磁盘 | $726.448 / 月 |
| Jev 输入 / 输出 | $0.042 / 百万输入 tokens；输出免费 |
| 10240 次正式 Jev 请求的真实输入 | 6727168 tokens，平均 656.95 / 次 |
| 上述正式请求的公开价估算 | $0.282541056，预热另计 |
| 相同支付输入配比的 Jev 成本 | $27.5919 / 百万次单步决策 |
| EC2 计算费交点 | 约 2586 万次/月，平均约 9.84 次/秒 |
| 四场景等权的两步路由输入 | 平均 2805.75 tokens / 完整路由 |
| Jev 两步路由成本 | $117.8415 / 百万次完整路由 |
| 两步路由的 EC2 计算费交点 | 约 606 万次完整路由/月 |

公式：`Jev 成本 = 实际输入 tokens × 0.042 / 1,000,000`；`EC2 月计算费 = 0.9776 × 730`；`交点请求数 = EC2 月计算费 / Jev 每次费用`。Jev 的 token 按其实际 usage 计算，没有用 Decider 的 373.9 token 替代。

**这些是公开价格和真实用量支持的费用估算，不是实际账单。g6.2xlarge 尚未进行本批性能测试，不能把 g6.xlarge 吞吐当作其容量保证。** 两者基础网络、代理、日志、运维、冗余、税费、折扣和所选目标模型执行费用未纳入交点；EBS 在单独一行列明。短时压测也不证明能持续满足一个月的负载。

[费用计算数据](sources/cost-calculation.json) · [AWS 计算价格响应](sources/aws-g6.2xlarge-pricing.json) · [gp3 价格响应](sources/aws-gp3-pricing.json) · [实例规格](sources/g6.2xlarge-hardware.json) · [Jev 官方价格页面文本](sources/jev-pricing-page.txt) · [原始用量汇总与文件哈希](sources/vllm/requests-usage.json)。

## 构建与验证

```bash
uv run --no-project --with python-pptx --with pillow --with cairosvg \
  --with matplotlib python scripts/build_presentation_v9.py

# 使用 LibreOffice 导出同目录 PDF 后检查渲染、保留页面与预览
uv run --no-project --with python-pptx --with pillow --with pymupdf \
  python scripts/verify_presentation_v9.py
```

新页为可编辑文字、表格、流程及 AWS / Lucide 图标；实测截图保留为图片。构建使用已存记录，不调用模型、不启停 GPU、不修改线上部署。PDF 逐页渲染，检查文字完整性、形状边界和原 v8 正文 / 图片保留；总览与重点页另行目视检查。

Demo：https://d3i7ogfx5ml7dc.cloudfront.net/#routing

Repo：https://github.com/milan9527/StrandsDecider

vLLM API：https://d1e9udi8st2p3g.cloudfront.net/docs
