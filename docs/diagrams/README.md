# 演示图表

仓库提供三张 SVG 图，可直接在 GitHub 或浏览器中查看、下载：

1. **[AWS 部署架构](architecture.svg)**：私有 S3 + CloudFront OAC、内网 ALB / ECS、模型私有端点、DynamoDB 及 SageMaker GPU 生命周期。
2. **[Decider vs 普通大模型](model-comparison.svg)**：同一候选决策任务的两种调用方式，以及共同的应用执行策略。
3. **[加密支付完整流程](payment-workflow.svg)**：五步决策与沙盒执行、参考差异、资金保护、最终回复及模拟事件。

SVG 文件可用于 README 或演示材料，不依赖外部图片、字体下载或脚本；显示中文需要本机支持中文字体。

部署架构图采用 **AWS 官方服务 / 资源图标与架构图风格**：保留官方配色，区分 AWS Cloud、us-east-1、VPC 和私有子网边界。CloudFront 位于区域边界外，SageMaker / Bedrock 托管服务位于应用 VPC 外，通过私有端点访问；橙色虚线表示 GPU 生命周期控制。图标来源与版本见 [AWS 图标说明](aws-icons/README.md)。

在仓库根目录重新生成：

```bash
uv run python scripts/generate_diagrams.py
```

布局源文件是 [scripts/generate_diagrams.py](../../scripts/generate_diagrams.py)。修改生成器后重新运行可同步三张 SVG 图。GitHub 不包含 `.drawio` 文件。

图中的业务数据和交易工具均为模拟。普通大模型流程描述的是本项目实际采用的受限 JSON 决策调用，不代表所有生成式模型都必须预设候选项。实线表示请求 / 访问方向（响应省略），虚线表示控制路径或异常分支。
