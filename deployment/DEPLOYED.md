# 已部署环境

最近发布及验收日期：2026-10-09。

**访问地址：https://d30wbetbveqce3.cloudfront.net**

API 文档：https://d30wbetbveqce3.cloudfront.net/api/docs

**当前状态：GPU Spot 启停功能已部署，GPU 已释放。** `us-east-2` 三个 AZ 的候选 Spot 池返回容量不足；本次尚未成功启动 GPU 实例，因此 CUDA 推理、GPU 延迟和实际实例释放流程仍待验收。登录与 16 个场景的示例回放可用，真实推理需要先启动 GPU 并等待就绪。

| 项目 | 当前值 |
| --- | --- |
| AWS Region | `us-east-2` |
| CloudFormation stacks | `strands-decider-demo`、`strands-decider-demo-gpu` |
| Stacks 状态 | `UPDATE_COMPLETE` |
| CloudFront distribution | `E2OTYMNXHAUP4X` |
| CloudFront VPC Origin | `vo_016dHcrysO7DPfYCVYqwSK` |
| S3 bucket | `strands-decider-demo-frontendbucket-lmcuzhb95pgk` |
| VPC | `vpc-00641884e5c4ebfe7` |
| ECS cluster / API service | `strands-decider-demo` |
| API Task | 1 个健康 ARM64 Fargate Task，0.25 vCPU / 0.5 GiB |
| GPU service | `strands-decider-demo-gpu-model`，当前任务数 0 |
| GPU 实例 | Spot 专用 ASG，最小 0 / 最大 1，当前实例数 0 |
| Spot 候选规格 | `g6.xlarge`、`g6.2xlarge`、`g5.xlarge`，L4 / A10G 24GB |
| Spot 单价上限 | $0.55/小时，仅实例价格 |
| GPU 自动释放 | 闲置 30 分钟；启动等待超过 20 分钟后申请释放 |
| ECR API repository | `strands-decider-demo-api` |
| ECR model repository | `strands-decider-demo-model` |
| API 镜像 tag | `20261009-gpu-api2` |
| GPU 模型镜像 tag | `20261009-gpu1`，已构建并推送，CUDA 运行待验收 |
| 认证 | 自建用户名 / 密码，无 Cognito |
| DynamoDB 认证表 | `strands-decider-demo-auth` |
| 模型 | 官方 `StrandsAgents/strands-decider-2B-hobson-v19` |
| CloudWatch 日志组 | `/ecs/strands-decider-demo` |

## 本次已完成的验收

- S3 四项 Block Public Access 全部开启，AWS 返回 `IsPublic: false`。
- S3 匿名读取已上传的 `index.html` 返回 **403**；同一文件通过 CloudFront 返回 **200**。
- OAC 使用 `always` / `sigv4`，Bucket policy 的允许语句只授权上述 distribution ARN。
- API 使用 CloudFront VPC Origin 和内网 ALB；API Task 没有公网 IP，VPC 路由表没有互联网默认路由。GPU 端口只允许 API 安全组访问。
- GPU 停止时 `/api/ready` 返回 `200`，`/api/health` 返回 `connected: false`；示例接口成功，真实推理返回 `503`。
- 未登录及退出后访问业务 API 均返回 `401`；重放退出前的 Cookie 同样被拒绝。线上会话 Cookie 的 `Secure`、`HttpOnly` 和 `SameSite=Strict` 已验证。
- 浏览器验证通过：用户名登录、错误密码、刷新保持登录、退出、API 访问控制、16 个场景、分类与搜索、场景说明及修改提示、输入修改与错误提示、示例守卫分支、当前标签页运行记录、JSON 导出、390px / 320px 布局。
- GPU 停止状态浏览器检查通过：Spot 管理面板、实例数为 0、真实推理提示启动 GPU、示例仍可运行。
- 实际通过页面发起启动；ASG 请求为 `SpotTargetCapacity=1`、`OnDemandTargetCapacity=0`。AWS 返回 `UnfulfillableCapacity`，直接 Spot 启动诊断返回 `InsufficientInstanceCapacity`；G/VT Spot 配额为 64 vCPU，未耗尽。随后已停止请求，确认 ASG desired / instances 和模型服务 desired / running / pending 全为 0。
- DynamoDB 条件更新、管理员权限、并发推理占用、闲置释放、启动超时、先停止任务再终止实例、Spot 专用与价格上限均有自动化测试。实际运行实例的自动释放尚未验证。
- 91 项自动化测试、Ruff、JavaScript 语法检查、前端格式检查和两个 CloudFormation 模板检查通过。
- 临时 CodeBuild 构建 stack 和源文件 S3 bucket 已清理。
- 工作台和工具调用守卫显示真实单项耗时与整次请求总时间，运行记录和 JSON 导出保留计时数据；示例回放不提供虚构的推理耗时。

GPU 关闭后，GPU 实例与其根卷不持续计费；常驻 Fargate API、ALB、VPC interface endpoints 等资源仍有费用。管理员可稍后重新点击「启动 GPU」请求 Spot 容量，不会自动改为按需 GPU。

## 既有 CPU 验收记录

迁移前，CPU 模型镜像曾在无互联网网络的 Docker 中通过真实推理；客服三问题推理曾观测约 8.33 秒。扩展场景记录位于本机 `.deployment/scenarios-live.json` 和 `.deployment/crypto-scenarios-live.json`。这些是 CPU 历史结果，不能作为 GPU 性能或准确率依据。

“加密货币支付”分类包含 USDC 未到账排查、USDT 少付处理、稳定币退款审批、商户结算延迟，每个场景 3 个决策。输入为模拟支付系统快照，不连接钱包、不广播交易。

更新、日志查看与清理说明见 [README.md](README.md)。本文件记录上述验收时点的环境；后续发布输出以 `.deployment/outputs.json`、`.deployment/gpu-outputs.json` 和 CloudFormation 为准。

管理员用户名 `admin`；强随机密码保存在本机 `.deployment/admin-credentials.json`，文件权限 0600。密码不写入本文档、前端或镜像。账号创建、停用与密码重置命令见 [README.md](README.md#登录与账号管理)。
