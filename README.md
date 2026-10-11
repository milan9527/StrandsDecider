# Strands Decider · 决策实验室与加密支付业务台

让 **Strands Decider** 与 **Amazon Bedrock GPT-6.1 Sol** 处理同一笔业务，比较每一步的选择、耗时和执行结果。

**[在线演示](https://d3i7ogfx5ml7dc.cloudfront.net) · [支付流程对比](https://d3i7ogfx5ml7dc.cloudfront.net/#crypto) · [PPTX](docs/presentations/v6/Strands-Decider-模型原理与支付业务演示-v6-优化流程实测版-27页-20261011.pptx) · [PDF](docs/presentations/v6/Strands-Decider-模型原理与支付业务演示-v6-优化流程实测版-27页-20261011.pdf)**

基于 [Strands Decider 官方介绍](https://strandsagents.com/blog/introducing-strands-decider/)，使用 FastAPI + 原生 HTML/CSS/JavaScript。在线演示需使用现有账号登录。

## 演示内容

| 模块 | 功能 |
| --- | --- |
| 决策实验室 | 16 个场景，支持 `choice` / `noul` / `score`、可编辑上下文、工具调用守卫与逐项计时 |
| 支付流程对比 | 四个支付场景，双模型并排展示输入、选择、耗时、模拟执行和最终客服回复 |

支付流程：**客服受理 → 交易核验 → 风控审批 → 业务处置 → 回复结案**。

| 场景 | 观察重点 | 可推进的模拟事件 |
| --- | --- | --- |
| USDC 未到账 | 确认数 3/12 时如何处理 | 确认数达标 |
| USDT 少付 | 应付 100、到账 99.80 时如何处理 | 补足差额 |
| 稳定币退款 | 地址未验证、未审批时如何处理 | 验证地址、审批通过 |
| 商户结算延迟 | 超过结算时限后如何处理 | 结算到账 |

业务均为模拟，不连接钱包或广播链上交易。客服回复由应用根据实际执行结果生成。

## 开始对比

1. 登录「支付流程对比」，选择场景和「真实模型」；也可先用「规则回放」熟悉操作。
2. 选择测试方式，点击「开始对比」。
3. 查看每轮输入 / 输出、两侧耗时、实际执行和最终业务结果。
4. 在「客户对话与回复」推进模拟交易：固定／优化流程需重新运行，等待中的闭环会继续。可导出 JSON 复核。

| 测试方式 | 比较内容 |
| --- | --- |
| 固定流程 | 固定业务快照，完成五步判断，再分别执行两侧方案 |
| 优化流程 | 按场景精简输入、明确候选条件；保持证据不变，与固定流程比较 |
| 自主闭环 | 根据实际执行反馈继续判断，可自动推进模拟事件 |

规则回放不调用模型，不产生模型性能数据。详细操作见 [支付演示指南](deployment/CRYPTO.md)。

## 如何理解结果

固定／优化流程向两模型提供相同的业务事实、问题与候选条件。Decider 返回选择和概率；GPT 按要求返回候选 ID JSON，两侧使用相同的执行校验。闭环后续输入会随各自的执行结果变化。

- **速度**：比较每步及累计后端耗时；累计值包含通信和排队，不等于整轮页面等待时间。
- **选择**：查看原始建议与演示参考的差异；参考由项目定义，不代表通用准确率。
- **执行**：资金条件不足时挂起并继续客服跟进；处理完 `5/5` 步不等于资金业务完成。应用的保护调整不计为模型答对。

Decider 用于候选明确的结构化判断；本演示不比较自由长文本生成能力。判断机制、BERT 区别与参考策略见 [模型比较说明](docs/MODEL_COMPARISON.md)。

## 当前架构

![AWS 部署架构](docs/diagrams/architecture.svg)

| 组件 | 实现 |
| --- | --- |
| 前端 | 私有 S3 + CloudFront OAC，阻止所有 S3 公共访问 |
| 后端 | CloudFront `/api/*` → 内网 ALB → ECS Fargate / FastAPI |
| Decider | 官方 v19，ECS on EC2 On-Demand `g6.xlarge` / NVIDIA L4，常驻运行 |
| GPT | Amazon Bedrock GPT-6.1 Sol，reasoning effort `low` |
| 登录 | 自建用户名 / 密码与 Cookie 会话，DynamoDB 保存账号和会话 |

区域资源位于 `us-east-1`，Bedrock 使用美国跨区域推理配置。部署、费用与运维见 [AWS 部署指南](deployment/README.md)。

## 本地运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，前端无需构建。

```bash
uv sync
uv run python -m scripts.manage_users create admin \
  --generate-to .deployment/local-credentials.json
AUTH_COOKIE_SECURE=false uv run uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

打开 `http://localhost:8000`，使用生成的凭据登录。基础工作台选择示例模式；支付业务台选择规则回放。

真实模型接入、配置与测试命令见 [开发指南](docs/DEVELOPMENT.md)。登录后可访问 `/api/docs`。

## 相关文档

| 文档 | 内容 |
| --- | --- |
| [支付演示指南](deployment/CRYPTO.md) | 场景操作、输入优化、结果与计时口径 |
| [模型比较](docs/MODEL_COMPARISON.md) · [自主闭环](docs/CLOSED_LOOP.md) | 判断机制、执行反馈与停止条件 |
| [开发指南](docs/DEVELOPMENT.md) · [AWS 部署](deployment/README.md) | 本地模型、API、测试、部署与运维 |
| [架构与流程图](docs/diagrams/README.md) · [演示资料](docs/presentations/v6/README.md) | SVG、PPT、讲稿和真实截图 |
| [项目历史](docs/HISTORY.md) | 版本更新、部署迁移、历史实测与资料维护记录 |

模型实现与许可见 [Strands Decider 官方仓库](https://github.com/strands-labs/strands-decider)。本项目为独立教学演示。
