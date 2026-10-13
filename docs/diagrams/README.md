# 演示图表

仓库提供四张 SVG 图，可直接在 GitHub 或浏览器中查看、下载：

1. **[AWS 部署架构](architecture.svg)**：私有 S3 + CloudFront OAC、内网 ALB / ECS、后端对 EC2 Decider / Bedrock / DynamoDB 的调用、Jev Lambda 转发及 GPU 生命周期。
2. **[Decider vs Jev vs GPT](model-comparison.svg)**：同一候选决策任务的三条调用路径，以及共同的应用执行策略。
3. **[加密支付固定输入流程](payment-workflow.svg)**：五步决策与沙盒执行、参考差异、资金保护、业务完成判定及模拟事件。
4. **[自主反馈闭环](closed-loop.svg)**：三侧各自判断、执行、读取结果，等待事件或重判，以及预算、转人工和完成条件。

SVG 文件可用于 README 或演示材料，不依赖外部图片、字体下载或脚本；显示中文需要本机支持中文字体。

部署架构图采用 **AWS 官方服务 / 资源图标与架构图风格**：保留官方配色，区分 AWS Cloud、us-east-1、VPC 和私有子网边界。CloudFront 位于区域边界外，EC2 GPU 位于私有子网，Bedrock 托管服务位于应用 VPC 外；橙色虚线表示 GPU 生命周期控制。图标来源与版本见 [AWS 图标说明](aws-icons/README.md)。

图中简化了网络细节，ECS 后端直接连到 EC2 模型服务、Bedrock 和 DynamoDB，分别表示模型调用与数据访问；不单独绘制 Runtime / DynamoDB VPC Endpoint 节点。2026-10-11 起 GPU 使用 `g6.xlarge` 常驻运行，手动停止保留磁盘。v4 及更早 PPT 保留采集时的 SageMaker 架构，详见 [部署记录](../../deployment/DEPLOYED.md)。

Jev 在 AWS 账户边界外，紫色连线表示 ECS 通过 IAM 调用 Lambda，再访问 Typesafe HTTPS API。Lambda 使用托管网络出口，从 Secrets Manager 取密钥；图中省略其私有调用端点节点。具体权限与网络见 [Jev 指南](../JEV.md)。

最新 [v8 PPT](../presentations/v8/README.md) 第 11 页展示当前三模型架构，使用可编辑图形和相同的 AWS 图标：ECS Fargate 后端调用 EC2 Decider、Bedrock 和 Jev 转发服务。第 14–19 页展示预热后的四场景性能与实际界面，第 24–25 页展示输入优化。来源和测量方法保存在备注与配套文档。

在仓库根目录重新生成：

```bash
uv run python scripts/generate_diagrams.py
```

布局源文件是 [scripts/generate_diagrams.py](../../scripts/generate_diagrams.py)。修改生成器后重新运行可同步四张 SVG 图。GitHub 不包含 `.drawio` 文件。

图中的业务数据和交易工具均为模拟。普通大模型流程描述的是本项目实际采用的受限 JSON 决策调用，不代表所有生成式模型都必须预设候选项。实线表示请求 / 访问方向（响应省略），虚线表示控制路径或异常分支。
