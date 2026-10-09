# 演示图表

[strands-decider-demo.drawio](strands-decider-demo.drawio) 是原生、未压缩 XML 格式的 draw.io 文件，可直接在 diagrams.net 或 draw.io 桌面版中打开编辑。共有三个页面：

1. **AWS 部署架构**：私有 S3 + CloudFront OAC、内网 ALB / ECS、模型私有端点、DynamoDB 及 SageMaker GPU 生命周期。
2. **Decider vs 普通大模型**：同一候选决策任务的两种调用方式，以及共同的应用执行策略。
3. **加密支付完整流程**：五步决策与沙盒执行、参考差异、资金保护、最终回复及模拟事件。

SVG 文件与 draw.io 采用相同的节点、文字和连线定义，可用于 README 预览或演示材料。它们不依赖外部图片、字体下载或脚本；显示中文需要本机支持中文字体。

在仓库根目录重新生成：

```bash
uv run python scripts/generate_diagrams.py
```

布局源文件是 [scripts/generate_diagrams.py](../../scripts/generate_diagrams.py)。修改生成器后重新运行可同步全部产物；如直接在 draw.io 中修改，请另存文件，避免下一次生成覆盖手工编辑。

图中的业务数据和交易工具均为模拟。普通大模型流程描述的是本项目实际采用的受限 JSON 决策调用，不代表所有生成式模型都必须预设候选项。实线表示请求 / 访问方向（响应省略），虚线表示控制路径或异常分支。
