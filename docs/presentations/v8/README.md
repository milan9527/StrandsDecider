# Strands Decider × Jev × GPT · v8 · 30 页

基于 v7 更新三模型性能、四场景真实截图和测试结论。保留模型原理、JevBench、行为差异、输入优化与微调路线；页面聚焦对比，详细测量说明放在备注和本文。

- **[下载 PPTX](Strands-Decider-模型原理与支付业务演示-v8-三模型预热性能对比-30页-20261012.pptx)** · [查看 PDF](Strands-Decider-模型原理与支付业务演示-v8-三模型预热性能对比-30页-20261012.pdf)
- [30 页预览](slides-overview.png) · [逐页讲稿与来源](讲稿与来源.md)
- 重点页：[公开基准](page-09-preview.png) · [四场景数据](page-14-preview.png) · [少付差异](page-17-preview.png) · [闭环结果](page-23-preview.png) · [微调方案](page-27-preview.png)
- [原始输入输出](live-observations.json) · [Lambda 预热验证](lambda-warm-verification.json) · [截图来源](capture-manifest.json)
- [JevBench 快照](sources/jevbench-api-20261012.json) · [方法文本](sources/jevbench-method.txt)
- [构建记录](build-manifest.json) · [渲染检查](render-audit.json) · [保留的 v7](../v7/README.md)

## 内容安排

| 页码 | 内容 |
| --- | --- |
| 1–7 | 决策模型目的、System One、三模型定位与调用方式、Decider 原理、一页 BERT |
| 8–10 | JevBench 方法、公开排名与能力 / 速度取舍，附可点击来源 |
| 11–13 | 当前三模型 AWS 架构、四场景五步骤、真实输入输出界面 |
| 14–19 | 预热后性能总览、节点耗时、四场景逐步选择和实际截图 |
| 20–23 | 行为差异、实际业务结果、Jev 速度解释、一页闭环 |
| 24–27 | 已验证的输入优化、剩余错误、最小对照与领域微调方案 |
| 28–30 | 应用分工、总结、Demo / Repo 链接和二维码 |

第 6 页将“System One 请求”替换为“提交业务事实、问题与候选项”。第 8–10 页显示 JevBench 评测链接；第 10 页另有官方 Decider 模型卡链接。第 13、25 页去掉采集批次、版本沿用等说明。

## 最新性能与选择

2026-10-12，现网 `triple1` / API `20261012-triple1`。Decider v19 运行于常驻 EC2 `g6.xlarge` / L4；Jev 实际版本 `jev-1.13.0`；Bedrock 为 `us.openai.gpt-6.1-sol`，reasoning `low`，只输出候选 ID。

三个模型各预热一次，再运行四场景优化流程：**60 次正式调用全部成功**。每步三侧业务输入及指纹完全相同；GPT 另有输出格式约束。每格为 **五步累计后端耗时 · 与演示参考一致次数**：

| 场景 | Strands Decider | Jev | GPT-6.1 Sol |
| --- | ---: | ---: | ---: |
| USDC 未到账 | 0.557 s · 5/5 | 2.318 s · 5/5 | 8.537 s · 5/5 |
| USDT 少付 | 0.514 s · 4/5 | 1.896 s · 5/5 | 4.171 s · 5/5 |
| 稳定币退款 | 0.564 s · 4/5 | 2.112 s · 5/5 | 5.453 s · 5/5 |
| 商户结算 | 0.408 s · 5/5 | 2.003 s · 5/5 | 4.173 s · 5/5 |
| **20 步合计** | **2.043 s · 18/20** | **8.329 s · 20/20** | **22.335 s · 20/20** |
| 平均每次 | 102.2 ms | 416.5 ms | 1116.7 ms |
| 中位数 | 81.3 ms | 397.7 ms | 863.4 ms |
| 最小 / 最大 | 75.0 / 182.9 ms | 322.0 / 591.5 ms | 776.7 / 3283.9 ms |

Jev / Decider 耗时比为 **4.08×**，GPT / Decider 为 **10.93×**，GPT / Jev 为 **2.68×**。Jev 17/20 次低于 500 ms；正式首次客服受理为 **549.8 ms**。GPT 本轮 USDC 回复结案为 3283.9 ms，全部慢请求保留；未从输出推断 GPT 内部推理过程。

### 怎样排除 Lambda 冷启动

1. 三个模型分别预热一次，保存请求、响应及耗时，标记为不计入正式统计的样本。
2. 完整重跑四场景，不用旧结果拼接，也不从耗时中减去估算初始化时间。
3. CloudWatch 用浏览器请求时间窗找到唯一 Lambda `START`，再按 RequestId 匹配 `REPORT`。正式 20 次 Jev 调用均无 `Init Duration`，并复用 Jev 预热请求的同一个日志流 / 执行环境。
4. 将 3 次预热保存在 `warmups`，60 次正式记录保存在 `cases`；日志关联依据及局限见 [验证 JSON](lambda-warm-verification.json)。

这证明本项目 Lambda 转发服务在正式调用时已预热，**不证明上游 Jev 服务没有其他初始化，也不等于纯推理耗时**。当前每次调用仍新建客户端和 HTTPS 连接；`backend_total_ms` 包括通信、后端处理与排队。前后两轮有网络和模型响应波动，均值变化不能全部归因于预热。

三模型并发，列累计不能相加作为浏览器等待时间。每模型 20 个不同任务只各测一次；参考一致次数不是通用准确率，均值与中位数不代表稳定性能或 P95 / P99。

## 行为与业务结果

| 场景 | Decider | Jev / GPT | 实际结果 |
| --- | --- | --- | --- |
| USDC 未到账 | 等待确认、审批通过、挂起跟进 | 同样选择 | 确认 3/12，无入账、未结案 |
| USDT 少付 | 确认已达 20/12，却等待确认 | 请求补款 | 缺少 0.20 USDT，三侧均挂起资金 |
| 稳定币退款 | 地址未验证却检查通过 | 验证退款地址 | 执行器调整 Decider 审批；未退款 |
| 商户结算 | 识别超时、升级结算、持续跟进 | 同样选择 | 结算款未到，不对账结案 |

Decider 与参考不一致 2 次、执行保护调整 1 次；两者是不同指标。少付误选 confidence 0.8138，退款误选 0.2524，高置信也会错。三侧每场景均处理五步，但初始条件下均 **0/4 完成资金及结案**。模型给出建议、应用处理步骤、资金业务完成分别统计。

第 23 页复用 v7 的独立 USDC 闭环及真实截图：三侧各六次决策、一次模拟确认事件，最终均完成 129 USDC 模拟入账及结案。Decider 首轮核验误选 `settlement_verified`；执行检查仍等待确认，模拟器推进到 12/12 后重判完成。18 次闭环决策不进入上述 60 次速度统计；原始来源保存在 `loop_source`。

## JevBench 评测来源

- [Benchmark Heaven API 榜单](https://benchmarkheaven.com/jev-models/api)
- [评测方法](https://benchmarkheaven.com/jev-models/api#jev16-method)
- [Strands Decider 官方模型卡](https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v19)
- [Strands Decider 原始介绍](https://strandsagents.com/blog/introducing-strands-decider/)

采用 v7 已核对的 2026-10-12 公开快照与网页实际截图，board v1.7.46、27 个排名条目；本项目没有重跑 JevBench。这是 Benchmark Heaven 第三方评分，不是各厂商给自己的官方评分。

综合分采用能力、校准、速度、成本四轴等权调和平均，并对部分低分轴施加惩罚，**不等于答题准确率**。例如 Qwen3.8 27B 综合 0.0，但能力分为 96.4；不能解释为它答不对。Jev p50 为 239.1 ms，本项目为 397.7 ms，任务、网络与测量位置不同，不能直接相减计算代理开销。

榜单没有本项目 GPT-6.1 Sol 与 Strands v19 的对应行，不补造成绩。官方 Decider 另报公开子集 167/231 = 72.29%，不与榜单归一化分数混排。各行配置、权重、历史成本估算标记保留在第 9 页和原始数据中。

## 已验证的优化与后续方法

第 24–25 页复用 2026-10-11 输入优化前后对照：精简字段、明确条件适用范围，Decider 参考一致 **14/20 → 18/20**，保护调整 **4 → 1**；权重未变。Jev 未参加这次前后对照。字段和条件表述同时变化，不能单独归因；原始数据见 [优化记录](../../results/optimized-2026-10-11.json)。

当前少付核验和退款审批仍出错。后续建议构造最小条件对照、数字边界和语言变体，测试按场景拆分判断，再评估 LoRA / Pointer Head 领域适配。按案件、模板簇和时间划分训练与独立测试集；保留概率校准、执行保护与通用任务回归。尚未实施领域微调，也没有宣称新的提升幅度。

## 构建与检查

原 v7 / v6 PPTX 保持不变。四场景 20 张截图为本轮现网直接采集，界面数据未替换；闭环与公开基准截图保留原来源。正文使用可编辑文字、表格、流程以及 AWS / Lucide 图标；统计图同时提供 PNG / SVG。构建、页面渲染与文字完整性检查见上方记录。

```bash
# 使用已保存的真实数据重新生成，不调用模型
uv run --with python-pptx --with pillow --with cairosvg --with matplotlib \
  python scripts/build_presentation_v8.py

# 读取 CloudWatch，复核已保存的请求窗口，不调用模型
uv run --with boto3 python scripts/verify_presentation_v8_warm.py

# PDF 导出需要 LibreOffice 与 Noto Sans CJK 字体
libreoffice --headless --convert-to pdf --outdir docs/presentations/v8 \
  docs/presentations/v8/Strands-Decider-模型原理与支付业务演示-v8-三模型预热性能对比-30页-20261012.pptx
```

`capture_presentation_v8.py` 会产生 3 次预热和 60 次正式模型调用，已有观察文件时拒绝覆盖；下一轮测试须使用新输出目录。它只读取 GPU 状态，拦截启停请求。公开网页采集器沿用 `capture_jevbench_v7.py`。

Demo：https://d3i7ogfx5ml7dc.cloudfront.net/#crypto  
Repo：https://github.com/milan9527/StrandsDecider
