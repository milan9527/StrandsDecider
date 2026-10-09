# 已部署环境

最近发布及验收日期：2026-10-09。

**访问地址：https://d3i7ogfx5ml7dc.cloudfront.net**

API 文档：https://d3i7ogfx5ml7dc.cloudfront.net/api/docs

**当前状态：us-east-1 按需 GPU 已部署并完成验收，GPU 已停止，原实例和磁盘保留。** 已验证真实 CUDA 推理和停止后的复用启动；旧 us-east-2 环境已删除。登录页面点击「启动 GPU」即可再次运行真实模型。

| 项目 | 当前值 |
| --- | --- |
| AWS Region | `us-east-1` |
| CloudFormation stacks | `strands-decider-demo`、`strands-decider-demo-gpu` |
| Stacks 状态 | 两个 stack 均为 `UPDATE_COMPLETE` |
| CloudFront distribution | `EJSAOZVC0U08G` |
| CloudFront VPC Origin | `vo_ILrhtFA1TnuBlt4FNg1wn9` |
| S3 bucket | `strands-decider-demo-frontendbucket-sdeevobzfie4` |
| VPC | `vpc-0ad82a2ebf66384d8` |
| ECS cluster / API service | `strands-decider-demo` |
| API Task | 1 个健康 ARM64 Fargate Task，0.25 vCPU / 0.5 GiB |
| GPU service | `strands-decider-demo-gpu-model-ondemand`，按需启停 |
| GPU 实例 | `i-01bd22555b6f48d61`，`g5.xlarge`，A10G 24GB，`us-east-1f` |
| 购买方式 | On-Demand，最多 1 台，$1.006/小时计算费 |
| 保留磁盘 | `vol-0fe2e81ecc5bc6bad`，80GB 加密 gp3，约 $6.40/月 |
| GPU 自动停止 | 闲置 30 分钟；启动等待超过 20 分钟后停止，磁盘保留 |
| ECR API repository | `strands-decider-demo-api` |
| ECR model repository | `strands-decider-demo-model` |
| API 镜像 tag | `20261009-ondemand2` |
| GPU 模型镜像 tag | `20261009-gpu1`，摘要一致且 CUDA 运行验收通过 |
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
- 按需 GPU 已完成首次创建、镜像拉取、模型预热，ECS GPU Task 健康；`/api/health` 报告 `device: cuda`。
- 页面停止后，EC2 进入 `stopped`，GPU 服务任务数归零，80GB 加密磁盘保持挂载；再次点击启动复用了同一实例 ID、同一磁盘 ID 和同一模型镜像摘要，ECS Task 再次健康。
- 重启后再次通过 CUDA 健康检查、真实决策接口及全部 4 个加密货币支付场景；每个场景三个决策的后端总耗时约 227–229 ms。
- 复测结束后再次通过页面正常停止，最终 EC2 状态为 `stopped`、模型任务数为 0，同一块磁盘仍挂载。停止状态的浏览器、示例回放、鉴权、S3/OAC 和私有网络检查全部通过。
- 浏览器真实模型推理通过，4 个加密货币支付场景的 12 个决策全部完成，保留逐项实测时间。
- 96 项自动化测试通过，覆盖 DynamoDB 条件更新、管理员权限、推理占用、闲置停止、启动超时、先停止任务再停止实例、容量不足时跨 AZ / 规格重试、结果不确定时幂等重试，以及复用已停止实例。
- Ruff、JavaScript 语法与 CloudFormation 模板检查通过。30 分钟闲置逻辑由自动化测试覆盖，未额外让线上实例空转 30 分钟。
- 临时 CodeBuild 构建 stack 和源文件 S3 bucket 已清理。
- 工作台和工具调用守卫显示真实单项耗时与整次请求总时间，运行记录和 JSON 导出保留计时数据；示例回放不提供虚构的推理耗时。

GPU 停止后不收 EC2 计算费；80GB 根卷约 $6.40/月，以及常驻 Fargate API、ALB、VPC interface endpoints 等费用继续。管理员点击「启动 GPU」会复用此实例和磁盘。停止不保留显存，启动仍需要加载模型。

## GPU 实测

2026-10-09，A10G 24GB，官方 v19 模型，逐项执行模式。以下为一次运行的后端总耗时，包含三个模型请求和服务端排队，不含浏览器往返网络；不代表性能或模型准确率保证。

| 场景 | 决策数 | 后端总时间 |
| --- | --- | --- |
| USDC 未到账排查 | 3 | 236.5 ms |
| USDT 少付处理 | 3 | 235.0 ms |
| 稳定币退款审批 | 3 | 232.3 ms |
| 商户结算延迟 | 3 | 229.7 ms |

首次约 6.64 GiB 镜像下载耗时约 124 秒。保留磁盘后，从页面点击启动到显示 GPU 就绪实测 **231.3 秒（约 3 分 51 秒）**，包含每分钟控制器协调、EC2 开机、模型加载和健康检查等待。重启任务使用本地缓存镜像，没有再次拉取镜像；实例启动到模型 HTTP 服务启动约 2 分钟。这是本次观测值，后续启动时间会变化。

## 区域迁移

所有应用区域资源部署到 `us-east-1`；CloudFront 与 IAM 为全球资源。GPU 候选可用区为当前账号的 `us-east-1d`、`us-east-1b`、`us-east-1c`、`us-east-1a`、`us-east-1f`。

- 已迁移管理员账号，密码不变；新域名需要重新登录。
- 已复制 9 个镜像版本，逐一核对源、目标 ECR 摘要一致。
- 旧日志归档到 us-east-1 的 `/strands-decider-demo/migrated-us-east-2/ecs`、`gpu-controller`、`gpu-build` 日志组，保留期沿用 14 / 7 天。
- us-east-2 两个旧 stack、旧 VPC、保留的 S3 / ECR / 认证表 / 日志及旧任务定义已删除，旧 CloudFront 地址已失效；删除后复查未发现上述项目活动资源。

## 既有 CPU 验收记录

迁移前，CPU 模型镜像曾在无互联网网络的 Docker 中通过真实推理；客服三问题推理曾观测约 8.33 秒。扩展场景记录位于本机 `.deployment/scenarios-live.json` 和 `.deployment/crypto-scenarios-live.json`。这些是 CPU 历史结果，不能作为 GPU 性能或准确率依据。

“加密货币支付”分类包含 USDC 未到账排查、USDT 少付处理、稳定币退款审批、商户结算延迟，每个场景 3 个决策。输入为模拟支付系统快照，不连接钱包、不广播交易。

更新、日志查看与清理说明见 [README.md](README.md)。本文件记录上述验收时点的环境；后续发布输出以 `.deployment/outputs.json`、`.deployment/gpu-outputs.json` 和 CloudFormation 为准。

管理员用户名 `admin`；强随机密码保存在本机 `.deployment/admin-credentials.json`，文件权限 0600。密码不写入本文档、前端或镜像。账号创建、停用与密码重置命令见 [README.md](README.md#登录与账号管理)。
