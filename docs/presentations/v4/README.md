# 决策模型与支付业务演示 · v4

> 最新版本：[v6 优化流程实测版](../v6/README.md) 包含当前 EC2 架构及两页真实优化演示；此页与 v4 PPT/PDF 保留历史内容。

**25 页**，参考原始《Strands-Decider-模型原理与支付业务演示.pptx》重新组织故事线：**为什么需要决策模型 → Jev 与 Strands Decider → 工作原理 → 支付对比 → 实测与结论 → Demo / Repo**。

- **[下载 PPTX](Strands-Decider-模型原理与支付业务演示-v4-决策模型与支付对比-25页-20261010.pptx)**
- [查看 PDF](Strands-Decider-模型原理与支付业务演示-v4-决策模型与支付对比-25页-20261010.pdf)
- [第 22 页对比说明预览](page-22-preview.png)
- [逐页讲稿与来源](讲稿与来源.md)
- [构建与原版对应记录](build-manifest.json)
- [官方资料核对记录](source-manifest.json)
- [上一版 v3](../v3/README.md)

## 故事线与页码

| 页码 | 讲述内容 |
| --- | --- |
| 1–2 | 让小模型做好高频决策：软件需要大量明确、聚焦的判断 |
| 3–4 | 决策模型 / System One；Choice、Noul、Score；Jev 与 Decider 的定位 |
| 5–8 | Decider 候选评分原理、与 GPT 的路径对比、BERT 一页比较、适用场景 |
| 9–11 | 项目架构、支付场景、相同输入与独立执行的比较方法 |
| 12–16 | 实际输入输出、五步耗时、候选评分差异、业务结果、退款执行保护 |
| 17–18 | **反馈执行仅两页**：证据更新后继续推进，以及两组业务的最终结果 |
| 19–22 | 累计、场景、节点耗时对比；选择差异和调用失败 |
| 23–25 | 任务分工建议、总结、Demo 与 Repo 地址及二维码 |

沿用原版“目的、原理、应用、项目、实测、结论”的顺序，保留 v3 中清晰的流程图、AWS 官方服务图标、速度图表和真实界面截图。BERT 仍为一页；没有 GPU 操作提示。原始文稿、v2、v3 均保留。

第 22 页改为“比较什么 / Decider / GPT / 怎么理解”四列表，分别解释累计耗时、调用成功、业务规则符合次数与商户结算执行情况。页面明确说明为何只比较 19 组，并用“普通收款是否需要退款审批”的例子解释规则差异，替换原先含义不够清晰的“单次样本 / 更符合演示策略”表述。

## Jev 介绍的依据

| 内容 | 官方依据 |
| --- | --- |
| System One 对状态返回类型化答案和概率 | [TypeSafe System One](https://docs.typesafe.ai/concepts/system-one) |
| Choice / Score / Noul；多个问题共享状态、独立评估 | [TypeSafe Introduction](https://docs.typesafe.ai/introduction) |
| Jev 的产品定位、RLCD 与官方 API 方向 | [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) |
| Decider 的开源实验定位、Pointer Head、用途 | [Strands 官方博客](https://strandsagents.com/blog/introducing-strands-decider/) |
| 本项目采用的 v19 底座、适配器与问题类型 | [官方模型卡](https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v19) |

Jev 作为决策模型类别与产品背景介绍，**未接入本项目、未进行速度或质量实测**。没有把 Jev 官网的性能倍数移用于本项目，也不假设 Jev 和 Decider 的内部架构相同或 API 完全兼容。输出类型受约束不等于业务答案必然正确；置信信息需要结合业务数据验证。

## 实测与截图

继续使用 **2026-10-10 12:26 UTC 起**的真实采集，本次仅重组文稿，没有重新调用模型。

- **固定输入**：19 组成功同输入配对；Decider 累计 1.810 s，GPT 22.068 s，比值约 12.20×。
- **失败**：GPT 另有 1 次 `ReadTimeoutError`，其结算方案未执行；成功耗时排除这次请求与对应的 Decider 请求。
- **反馈执行**：USDC 每侧 6 次决策，退款每侧 9 次决策，双方均完成模拟业务。两侧后续输入可能不同，不合入固定配对统计。
- **时间**：`backend_total_ms` 包括服务通信与排队；不等于浏览器全程等待，不包含现实外部事件等待。
- **输出**：模型选择、应用执行和模拟事件分别解释；客服回复来自应用模板。

来源：[固定输入数据](../../results/benchmark-2026-10-10.json)、[反馈执行记录](../v2/loop-observations.json)、[截图记录](../v2/capture-manifest.json)、[v3 裁剪记录](../v3/build-manifest.json)。原始文稿与 v3 源文件哈希、原版页码对应关系记录在 `build-manifest.json`。

## 演示入口

- **Demo**：https://d3i7ogfx5ml7dc.cloudfront.net/#crypto
- **GitHub Repo**：https://github.com/milan9527/StrandsDecider

末页包含完整可点击地址与对应二维码。Demo 使用现有账号登录，私有仓库需要访问权限；文稿不包含凭据。

## 重新生成

原始 PPTX 由维护者另行提供，其余素材使用仓库内的 v3 文稿、图标与既有证据：

```bash
uv run --with python-pptx --with pillow --with cairosvg --with qrcode \
  python scripts/build_presentation_v4.py \
  --base /path/to/Strands-Decider-模型原理与支付业务演示.pptx

libreoffice --headless --convert-to pdf --outdir docs/presentations/v4 \
  docs/presentations/v4/Strands-Decider-模型原理与支付业务演示-v4-决策模型与支付对比-25页-20261010.pptx
```

模型与流程主要使用可编辑文本和形状；图标来源见 [Lucide 许可](../v3/icons/README.md) 与 [AWS 官方素材](../../diagrams/aws-icons/README.md)。验证结果见 `render-audit.json`。
