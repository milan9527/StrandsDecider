# Strands Decider · 优化流程实测版 v6 · 27 页

基于最新 v5 增加两页，用现网界面和四场景真实记录说明 Decider 的输入优化。保留第 14 页审批差异解释，以及此前删除重复来源页脚的修改。

- **[下载 PPTX](Strands-Decider-模型原理与支付业务演示-v6-优化流程实测版-27页-20261011.pptx)**
- [查看 PDF](Strands-Decider-模型原理与支付业务演示-v6-优化流程实测版-27页-20261011.pdf)
- [第 23 页：USDC 优化方法与选择变化](page-23-preview.png)
- [第 24 页：四场景实测结果与速度](page-24-preview.png)
- [全部 27 页预览](slides-overview.png)
- [逐页讲稿与来源](讲稿与来源.md)
- [构建记录](build-manifest.json) · [截图来源](capture-manifest.json) · [渲染检查](render-audit.json)
- [保留的 v5 版本](../v5/README.md)

## 两页新增内容

| 页码 | 演示内容 |
| --- | --- |
| 23 | 真实界面的「优化流程」入口；普通收款去除无关退款字段、明确候选适用范围；同一 USDC 证据下，Decider 从等待人工审批变为规则检查通过，GPT 两次均检查通过 |
| 24 | 四场景参考一致次数、累计后端耗时、保护调整次数，以及 USDC 优化流程的真实速度截图；保留少付核验、退款审批两项剩余差异 |

原结尾三页顺延为 25–27 页，第 26 页总结同步加入优化观测；最后一页继续保留 Demo / Repo 链接及二维码。原 v5 PPT/PDF 不覆盖。

本项目优化的是 **输入字段与候选条件表述**：候选 ID 集合、模型权重、演示参考和执行校验均保持一致，没有领域微调，也没有把参考答案输入模型。两模型收到同一种配置下相同的业务输入。字段精简与条件改写同时进行，不能单独把效果归因于某一个字段。

## 真实观测及限制

来源为 [2026-10-11 四场景实测](../../results/optimized-2026-10-11.json)：EC2 `g6.xlarge` / L4 常驻运行，Decider v19 对比 Bedrock GPT-6.1 Sol（reasoning `low`），API `20261011-optimized1` / 前端 `optimized1`。

| 指标 | 固定流程 | 优化流程 |
| --- | --- | --- |
| Decider 与演示参考一致 | 14/20 | 18/20 |
| GPT 与演示参考一致 | 20/20 | 20/20 |
| Decider 累计后端耗时 | 2.059 秒 | 1.578 秒 |
| GPT 累计后端耗时 | 18.694 秒 | 23.174 秒 |
| Decider 保护调整 | 4 次 | 1 次 |

80 次真实模型调用全部成功，每种配置、每个模型各 20 次。每场景先固定后优化、只执行一次，未随机化或重复采样；参考一致不是通用准确率，顺序、缓存、网络及排队也可能影响耗时，不能宣称稳定提速。

第 23 页 USDC 审批单步，Decider 为 **75.7 → 80.2 ms**，该单步没有提速；改善的是选择。截图中的 **390.9 ms / 9.77 s** 是 USDC 优化流程五步累计，与第 24 页表格的四场景累计分开标注。确认数仍为 3/12，审批检查通过不等于资金到账。

优化后，Decider 仍在少付核验中误选等待确认、在退款审批中过早选择检查通过。后端保留原始建议和保护调整，不能把应用纠正计为模型答对。

原有 2026-10-10 图表与截图保留其 SageMaker 采集口径，来源在备注和讲稿中说明；新增两页使用 2026-10-11 EC2 的独立批次，不合并统计。本次文稿编辑没有重新调用模型：速度截图来自已完成的真实测试，仅矩形裁剪；优化入口另外以现网界面高分辨率截取，未运行决策。截图没有改写数值或文字。

## 演示入口与代码

- Demo：https://d3i7ogfx5ml7dc.cloudfront.net/#crypto
- Repo：https://github.com/milan9527/StrandsDecider
- [操作与四场景说明](../../../deployment/CRYPTO.md)
- [输入字段与候选适用条件](../../../app/crypto_profiles.py)
- [模型选择与执行保护的区别](../../MODEL_COMPARISON.md)

## 重新生成

```bash
uv run --with python-pptx --with pillow --with cairosvg \
  python scripts/build_presentation_v6.py

libreoffice --headless --convert-to pdf --outdir docs/presentations/v6 \
  docs/presentations/v6/Strands-Decider-模型原理与支付业务演示-v6-优化流程实测版-27页-20261011.pptx
```

构建器读取仓库内 v5 PPT、实测 JSON、截图及图标；新增文字、表格和对比卡片均可编辑。截图及裁剪坐标有哈希记录，可复核来源。

已验证 27 页 PPT/PDF、全部备注、文字渲染与页面边界、数据及截图来源、末页链接和两个二维码；新增页及总结页已完成目视检查，原 v5 PPT/PDF 哈希保持不变。
