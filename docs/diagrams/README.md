# 演示图表

仓库提供四张 SVG 图，可直接在 GitHub 或浏览器中查看、下载：

1. **[AWS 部署架构](architecture.svg)**：私有 S3 + CloudFront OAC、内网 ALB / ECS、文字 vLLM 与图片视觉服务、Bedrock / DynamoDB、Jev 转发及密钥注入。
2. **[Decider vs Jev vs GPT](model-comparison.svg)**：同一候选决策任务的三条调用路径，以及共同的应用执行策略。
3. **[加密支付固定输入流程](payment-workflow.svg)**：五步决策与沙盒执行、参考差异、资金保护、业务完成判定及模拟事件。
4. **[自主反馈闭环](closed-loop.svg)**：三侧各自判断、执行、读取结果，等待事件或重判，以及预算、转人工和完成条件。

SVG 文件可用于 README 或演示材料，不依赖外部图片、字体下载或脚本；显示中文需要本机支持中文字体。

部署架构图采用 **AWS 官方服务 / 资源图标与架构图风格**：保留官方配色，区分 AWS Cloud、us-east-1、VPC 和私有子网边界。CloudFront 位于区域边界外，API 位于应用 VPC 的私有子网，vLLM 位于另一 VPC；橙色虚线表示启动时注入密钥。图标来源与版本见 [AWS 图标说明](aws-icons/README.md)。

图中简化了网络细节，ECS 后端直接连到 EC2 模型服务、Bedrock 和 DynamoDB，不单独绘制网络端点。文字决策通过 VPC Peering 调用共享 vLLM `g6.xlarge`；2026-10-23 新增图片决策，通过同一应用 VPC 的 TCP 18123 调用另一台现有 `g6.xlarge` 上的官方视觉服务。两路独立计时，不将图片原生推理称为 vLLM。历史 PPT 保留其采集时的架构与数据，详见 [部署记录](../../deployment/DEPLOYED.md)。

Jev 在 AWS 账户边界外，紫色连线表示 ECS 通过 IAM 调用 Lambda，再访问 Typesafe HTTPS API。Lambda 使用托管网络出口，从 Secrets Manager 取密钥；图中省略其私有调用端点节点。具体权限与网络见 [Jev 指南](../JEV.md)。

历史 [v8 PPT](../presentations/v8/README.md) 第 11 页展示当时的原版 EC2 三模型架构。第 14–19 页为该批四场景性能与界面，第 24–25 页为输入优化；本次 SVG 更新不改写历史 PPT。

在仓库根目录重新生成：

```bash
uv run python scripts/generate_diagrams.py
```

布局源文件是 [scripts/generate_diagrams.py](../../scripts/generate_diagrams.py)。修改生成器后重新运行可同步四张 SVG 图。GitHub 不包含 `.drawio` 文件。

图中的业务数据和交易工具均为模拟。普通大模型流程描述的是本项目实际采用的受限 JSON 决策调用，不代表所有生成式模型都必须预设候选项。实线表示请求 / 访问方向（响应省略），虚线表示控制路径或异常分支。
