# AWS 中文博客稿：Strands Decider 实践

约 6000 字重写版，按照“支付业务需求 → 模型原理与适用范围 → AWS 部署 → 支付实测与优化 → 模型路由 → vLLM 并发 → 成本与实践结论”组织，包含 5 张配图、3 张数据表、一个请求示例和一个 CLI 示例。

- **[可编辑 Word](Strands-Decider-AWS实践.docx)**
- [Markdown 正文](Strands-Decider-AWS实践.md)
- [网页预览](Strands-Decider-AWS实践.html)，图片已内嵌，可单独打开
- [PDF](Strands-Decider-AWS实践.pdf)，由同一正文的网页版本导出
- [图表来源](figure-sources.json) · [构建记录](build-manifest.json) · [渲染检查](render-audit.json)

正文按“中文字符 + 英文及数字词”统计为 **6256 字/词**，其中中文字符 5775，包含标题、表格与图注，不含代码和参考资料。Word 中的文字、表格可以编辑，截图保持原始内容。叙事调整与参考文章的具体对应见 [写作说明](写作说明.md)。

## 配图与证据

| 图 | 内容 | 来源 |
| --- | --- | --- |
| 1 | 候选评分与业务执行反馈 | 依据 [官方介绍](https://strandsagents.com/blog/introducing-strands-decider/)与项目执行流程绘制；[SVG](assets/05-decision-flow.svg)、[PNG](assets/05-decision-flow.png) |
| 2 | AWS 简版部署架构 | 依据当前部署绘制，使用仓库内 AWS 官方服务图标；[SVG](assets/01-aws-architecture.svg)、[PNG](assets/01-aws-architecture.png) |
| 3 | 退款审批输入、模型原始选择与实际执行 | [v8 实际截图](../../presentations/v8/screenshots/refund-decision.png)，未改写图片数据 |
| 4 | 中英文工单索引的三模型路由 | [完整实测截图](../../results/workflow-routing-2026-10-13/retrieval-desktop.png)的结果区域裁剪；裁剪坐标保留在 [v9 构建记录](../../presentations/v9/build-manifest.json) |
| 5 | 原版与 vLLM 同机吞吐 | [v9 图表](../../presentations/v9/assets/original-vllm-rps.png)，由 [原版数据](../../presentations/v9/sources/vllm/original-benchmark.json)与 [vLLM 完整复测](../../presentations/v9/sources/vllm/vllm-recheck.json)生成 |

支付、路由、原版同机对照和 Jev 直连性能来自不同批次，正文分别交代了环境与统计口径。成本使用 [v9 的官方价格快照和实测用量计算](../../presentations/v9/sources/cost-calculation.json)。g6.2xlarge 只用于成本估算，本次没有增加该机型性能测试。图标来源见 [AWS 图标说明](../../diagrams/aws-icons/README.md)。

## 写法参考

参考用户提供文章的业务切入、架构说明、实测表格和应用取舍方式，未复制其正文：

- [以 Kiro 快速部署云上 Agent](https://aws.amazon.com/cn/blogs/china/kiro-quick-deploy-agent-deploy-amazon-bedrock-agentcore/)
- [Amazon Bedrock AgentCore 数据持久化文件系统](https://aws.amazon.com/cn/blogs/china/amazon-bedrock-agentcore-file-system-session-storage-amazon-efs-s3-files/)
- [基于 AgentCore 构建自学习、可进化的文旅行业近似信息抽取 Agents](https://aws.amazon.com/cn/blogs/china/self-learning-evolvable-agents-for-cultural-tourism-info-extraction-with-agentcore/)

## 更新正文与导出

先编辑 Markdown，再运行：

```bash
uv run --no-project --with python-docx --with markdown \
  --with beautifulsoup4 --with pillow --with cairosvg \
  python scripts/build_decider_blog.py
```

该脚本生成 Word、含内嵌图片的 HTML、架构图与来源清单，不发起模型调用。再导出 PDF 并检查图片、全文及桌面和手机溢出：

```bash
uv run --no-project --with playwright --with pymupdf --with python-docx \
  --with beautifulsoup4 --with pillow python scripts/render_decider_blog.py \
  --browser /path/to/chromium
```

也可省略 `--browser` 使用 Playwright 已安装的默认 Chromium。PDF 更新后需检查分页预览。发布到博客平台时，可从 `assets/` 上传原始 PNG，并替换 Markdown 图片地址。
