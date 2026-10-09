# 已部署环境

最近发布日期：2026-10-09。

**访问地址：https://d3i7ogfx5ml7dc.cloudfront.net**

API 文档：https://d3i7ogfx5ml7dc.cloudfront.net/api/docs

**2026-10-09：SageMaker Endpoint 已为 `InService`，真实 CUDA 推理已通过验收。独立的加密支付业务台已上线，并完成 Bedrock GPT-6.1 Sol 与 Decider 的真实对比。** 原 EC2 已停止，80GB 磁盘保留作为回退。项目区域资源位于 `us-east-1`；CloudFront 和 IAM 为全球资源。Bedrock 使用美国跨区域推理配置。

**加密支付业务台：https://d3i7ogfx5ml7dc.cloudfront.net/#crypto**。演示路线、比较口径与实测结果见 [CRYPTO.md](CRYPTO.md)。

| 项目 | 当前值 |
| --- | --- |
| AWS Region | `us-east-1` |
| CloudFormation stacks | `strands-decider-demo`、`strands-decider-demo-gpu`、`strands-decider-demo-sagemaker` |
| Stacks 状态 | 三个 stack 均为 `UPDATE_COMPLETE` |
| CloudFront distribution | `EJSAOZVC0U08G` |
| CloudFront VPC Origin | `vo_ILrhtFA1TnuBlt4FNg1wn9` |
| S3 bucket | `strands-decider-demo-frontendbucket-sdeevobzfie4` |
| VPC | `vpc-0ad82a2ebf66384d8` |
| ECS cluster / API service | `strands-decider-demo` |
| API Task | 1 个 ARM64 Fargate Task，0.25 vCPU / 0.5 GiB |
| 模型托管 | SageMaker 实时推理，`ml.g6.xlarge`，L4 24GB，最多 1 台 |
| SageMaker Endpoint | `strands-decider-demo-decider`，由控制器创建 / 删除 |
| SageMaker Model | `strands-decider-demo-decider-e919f42f408d` |
| SageMaker EndpointConfig | `strands-decider-demo-decider-e919f42f408d-gpu4` |
| GPU 参考计算价格 | $1.1267/小时，2026-10-09 查询 |
| GPU 自动停止 | 闲置 30 分钟删除 Endpoint；启动超过 20 分钟请求停止，Creating 阶段需等 AWS 创建结束后清理 |
| 原 EC2 | `i-01bd22555b6f48d61`，`g6.2xlarge`，`stopped`，`us-east-1f` |
| 原 GPU ECS service | `strands-decider-demo-gpu-model-ondemand`，任务数 0 |
| 原 EC2 控制器 | CloudFormation `ControllerState=DISABLED` |
| 保留磁盘 | `vol-0fe2e81ecc5bc6bad`，80GB 加密 gp3，约 $6.40/月 |
| ECR API repository / tag | `strands-decider-demo-api:20261009-crypto2` |
| ECR model repository / tag | `strands-decider-demo-model:20261009-sm1` |
| 认证 | 自建用户名 / 密码，无 Cognito |
| DynamoDB 认证表 | `strands-decider-demo-auth` |
| 模型 | 官方 `StrandsAgents/strands-decider-2B-hobson-v19` |
| API 日志组 | `/ecs/strands-decider-demo` |
| 模型日志组 | `/aws/sagemaker/Endpoints/strands-decider-demo-decider` |
| Bedrock 对比模型 | `us.openai.gpt-6.1-sol`，GPT-6.1 Sol，推理强度 `low` |
| Bedrock Runtime 私网端点 | `vpce-0d5bced25d7fabac2`，`available`，单子网，Private DNS 开启 |
| 前端版本 | `crypto5`，独立业务模块 `/static/crypto.js` 和 `/static/crypto.css` |

## 会话事件展示（crypto5）

- 「推进模拟交易」按钮移到客服会话面板；成功事件立即显示系统通知、前后数值、时间和证据版本。失败事件说明原因并明确证据未改变。
- 客户诉求、系统事件、两模型的模拟客服回复按时间保留，历史回复显示原证据版本；重新运行后追加新回复。每个案例独立保存最近 80 条，支持 JSON 导出，刷新 / 退出 / 重置时清除。
- 新事件清除旧决策与执行结果，仍需重新运行完整流程；事件通知不冒充模型回复。
- 同步新增 AWS 架构、模型对比和支付流程三张 SVG 图、项目 README、开发指南与不含凭据的最新实测摘录；部署架构使用 AWS 官方图标及 Cloud / Region / VPC / 私有子网边界。GitHub 不包含 `.drawio` 文件，本地保留可编辑版本。
- 本地与线上浏览器验证通过：确认数、补款、地址验证、审批及结算事件通知，失败事件、历史回复、证据版本、导出、重置和移动布局均正常。线上前端已核对为 `crypto5`，CloudFront invalidation `I9RCKRESMBOE9I8R98TW7KCUHI` 已完成；API 镜像保持 `20261009-crypto2`。
- 本轮会话验证使用明确标记的规则回放；既有真实模型验证见下文。记录保存在 `.deployment/crypto-conversation-browser.json` 和 `.deployment/crypto-conversation-local-browser.json`。

## 执行策略放宽（crypto4）

- 取消「模型动作必须等于演示参考」的执行门槛。分流、核验、保守审批和跟进选择可以保留参考差异，继续完成后续步骤。
- 两模型均使用同一执行策略。资金条件不足或人工复核未完成时挂起资金动作，提前结案转为跟进；这些步骤仍正常完成，进入客服回复。原始模型选择、实际动作及保护调整分别记录，不将后端调整算作模型正确输出。
- 客服回复与实际模拟订单状态一致；即便证据已经满足，模型选择挂起时也不会宣称已入账、已退款或已对账。
- 线上四个初始案例的真实模型复测通过：Decider 和 GPT-6.1 Sol 全部 **5/5 步完成**，没有人工修正。Decider 的 USDC 未到账审批差异原样保留，不再停在 2/5；其余资金或结案调整也继续走完整个流程。所有初始案例均为订单待处理、工单持续跟进。
- 本地页面验证通过：重现原 2/5 分支后完成 5/5，资金挂起后继续回复，保留模型原始输出，失败重试、导出及 320px / 390px 布局正常。**140 项自动化测试通过**，包括不同场景的资金前置条件、保守方案、提前结案和客服回复真实性。
- 后端镜像 `20261009-crypto2`、前端 `crypto4` 已部署；CloudFront invalidation：`I2WKA7W1RBVVHB05Z83M5WPCUU`。线上 HTML、主脚本和支付模块 JS / CSS 与本地内容一致。
- 线上浏览器验证通过：真实双模型完整流程、参考差异后继续五步、资金挂起与跟进回复、原始建议保留、调用失败与重试、账本、导出、手机布局及鉴权。AWS 部署核验通过，CloudFront invalidation 已完成；私有 S3 + OAC、私网 ECS / Bedrock / SageMaker、旧 EC2 停止并保留磁盘均正常。
- 本次原始记录：`.deployment/crypto-flexible-models-live.json`、`.deployment/crypto-flexible-local-browser.json`、`.deployment/crypto-flexible-browser-live.json`、`.deployment/crypto-flexible-verified-deployment.json`、`.deployment/crypto-flexible-tests.log`。

## 历史加密支付模块验收（crypto1–3）

- 四个独立案例覆盖客服受理、交易核验、风控审批、业务处置及回复结案；可修改交易证据、模拟补款 / 确认 / 地址验证 / 审批 / 结算到账。
- `crypto3` 增加「运行完整流程并对比」：生成建议后执行两套独立沙盒流程，自动定位结果区域。两侧最终订单、工单、模拟账本及客服回复并排显示；五步执行输出默认全部展开，含业务证据、规则拦截、执行失败、未执行步骤、人工修正记录和时间。
- 本次为前端发布，CloudFront invalidation：`IE9TIS9YM02DWQLQ17U6MM0N4`。线上 HTML、主脚本、支付模块 JS / CSS 已逐字节核对本地版本。API 镜像与 AWS 基础设施未更改。
- 新增结果展示浏览器验证通过：四个案例、双侧一键执行、待跟进 / 结案、规则拦截、执行服务失败及重试、模型失败时不执行、人工修正与历史保留、导出及 320px / 390px 布局。错误分支由浏览器明确注入规则回放响应，未计入模型性能结果。
- 真实退款流程一键验证通过：Decider 与 GPT-6.1 Sol 均执行 5/5 步，订单为模拟退款已登记、工单已结案，回复和账本完整显示。原始结果：`.deployment/crypto-results-browser-live.json`；本地回放验证：`.deployment/crypto-results-local-browser.json`。
- GPT-6.1 Sol 与 Decider 每步使用相同输入指纹，展示逐步动作、后端耗时、浏览器往返、合计、规则一致情况和原始响应。
- 线上完成 20 组真实配对决策：Decider 合计 1.70 秒、业务规则一致 14 / 20；GPT-6.1 Sol 合计 16.31 秒、业务规则一致 20 / 20。这是本次固定案例观测，不代表通用准确率。
- Decider 的 6 次规则偏差都被拦截，规则修正后完成各案例的沙盒流程，没有实际资金操作。
- 线上浏览器验证通过：真实双模型对比、证据失效与重新核验、审批前置条件、规则拦截、人工修正、客服回复、模拟退款账本、导出、320px / 390px 布局以及鉴权。
- 原有 16 个场景、真实模型工作台、工具调用守卫、计时、运行记录、导出、手机布局和登录 / 退出回归通过。
- **127 项自动化测试通过**；代码格式、JavaScript 语法、CloudFormation 模板检查通过。
- 新增 Bedrock Runtime 私网端点；IAM 和 endpoint policy 仅授权指定 GPT-6.1 Sol 推理配置与对应美国区域基础模型 ARN。
- 本次部署核验通过：CloudFormation `UPDATE_COMPLETE`，SageMaker GPU 就绪；S3 匿名访问 403、四项公共访问阻止与 OAC 授权正常；ECS 无公网 IP、ALB 为内网、VPC 无互联网默认路由，Bedrock 私网端点为 `available`。旧 EC2 仍停止，同一块 80GB 加密磁盘保留。
- 线上原始记录保存在本机 `.deployment/crypto-models-live.json` 和 `.deployment/crypto-browser-live.json`。

## SageMaker 发布与历史验收

- 原有 CUDA 镜像增加 SageMaker `/ping` 和 `/invocations` 适配层，权重和模型逻辑保持不变。
- 镜像摘要：`sha256:b4d81c2dac9a37cf8233b3f5cb1de9364219334a7612b6573c75ad9951767ba2`。
- 当前 API 镜像摘要：`sha256:defe21c0a398747df17ae6dcdcd2920965c13f6ac0d548a2b5f3a5706b2b14e7`。
- SageMaker 模型启用网络隔离；ECS 经 SageMaker Runtime 私有 VPC endpoint 发起签名调用，调用权限限定到上述 Endpoint。
- 停止操作等待正在执行的推理结束，再删除 Endpoint。下次启动重新分配硬件，保留模型镜像和配置；SageMaker 不使用旧 EC2 磁盘。
- 首次 `CreateEndpoint` 于 **2026-10-09 04:03:24 UTC** 被 AWS 接受，20 分钟内仍为 `Creating`，没有容器日志或 `FailureReason`。请求删除时 AWS 返回 `Cannot update in-progress endpoint`；控制器保留停止请求，等待 AWS 创建流程结束后删除。当前没有证据将此等待归因为特定容量或容器错误。
- 随后一次 Endpoint 创建时间为 **04:57:23 UTC**，`InService` 的最后修改时间为 **05:02:21 UTC**。当前实例数为 1；实际健康检查返回 `device: cuda`，旧 EC2 仍停止。上述 AWS 时间戳不等同于浏览器点击启动到就绪的实测时间。
- 113 项自动化测试通过，包含 API、身份认证、逐项计时、GPU 状态并发控制、SageMaker 协议、创建幂等、失败清理、闲置删除、启动超时，以及 AWS 无法取消创建时保留停止请求并在创建完成后删除。
- Ruff、Prettier、JavaScript 语法、CloudFormation 模板及补丁空白检查通过。
- 浏览器验证 SageMaker 错误展示、重试按钮、停止按钮状态和 320px 布局通过。此项使用浏览器内模拟错误，不代表 AWS 实际报错或实际推理成功。
- 修复后额外通过真实线上“等待创建结束后清理”的页面验证，按钮禁用和 320px 布局正常；控制器返回 `waiting_for_creation_before_delete`，不再把这个 AWS 限制作为未处理异常。
- 完整页面回归通过：登录、16 个场景、加密支付分类与搜索、输入编辑与错误提示、示例回放、工具守卫、计时、运行记录、导出、手机布局及退出。此轮未执行真实模型推理。
- 停止请求等待期间的部署核验通过：S3 匿名访问 403、四项公共访问阻止、OAC 分发授权、健康的私网 Fargate API、内网 ALB、无互联网默认路由、旧 EC2 已停止及保留磁盘、SageMaker Runtime 私有端点、登录 / 退出 / 会话重放防护。示例可用，真实模式返回 503。

启动、部署、IAM 和清理步骤见 [SAGEMAKER.md](SAGEMAKER.md)。

## 保留的应用功能与安全边界

- 前端私有 S3 + CloudFront OAC。S3 四项 Block Public Access 全部开启，Bucket policy 仅允许指定 CloudFront distribution；此前匿名访问 S3 返回 403，CloudFront 返回 200。
- API 使用 CloudFront VPC Origin 和内网 ALB，Fargate Task 无公网 IP，VPC 没有互联网默认路由。
- 自建用户名 / 密码登录，Cookie 使用 `Secure`、`HttpOnly`、`SameSite=Strict`，退出后会话失效。
- 16 个演示场景，包括 USDC 未到账排查、USDT 少付处理、稳定币退款审批、商户结算延迟。支付数据为模拟快照，不连接钱包或广播交易。
- 真实模式显示各个决策的实测耗时及整次请求总时间；运行记录和 JSON 导出保留计时。示例模式不虚构推理时间。
- GPU 停止时登录、场景浏览、示例回放仍可用，真实推理返回未就绪提示。

Endpoint 删除后停止 SageMaker GPU 计算计费；ECS API、ALB、VPC interface endpoints、ECR 和保留的 EC2 磁盘等费用继续。

## EC2 历史验收

切换 SageMaker 前，官方 v19 模型曾在 `g5.xlarge` A10G 24GB 上通过 CUDA 推理；4 个加密货币支付场景每场景 3 个决策，总耗时约 227–237 ms。复用已停止实例和缓存磁盘启动实测 231.3 秒。

这些是 **EC2 历史结果，不能作为 SageMaker 性能结果**。随后原可用区出现 `InsufficientInstanceCapacity`，同一停止实例尝试 `g6.xlarge` 和 `g6.2xlarge` 仍无法启动。当前保留实例规格为 `g6.2xlarge`，处于停止状态，磁盘未删除。保留磁盘不会预留 GPU 容量。

## 区域迁移历史

- 已将应用迁移到 `us-east-1`，管理员密码不变。
- 迁移时复制 9 个镜像版本并核对 ECR 摘要。
- 旧日志归档到 us-east-1 的 `/strands-decider-demo/migrated-us-east-2/ecs`、`gpu-controller`、`gpu-build` 日志组。
- us-east-2 的旧 stack、VPC、S3、ECR、认证表、日志和任务定义已删除，旧 CloudFront 地址失效。

本文件记录上述发布时点；实时状态以 CloudFormation、SageMaker 及 `.deployment/outputs.json`、`.deployment/sagemaker-outputs.json` 为准。

管理员用户名 `admin`；密码保存在本机 `.deployment/admin-credentials.json`，权限 0600，不写入文档、前端或镜像。账号管理见 [README.md](README.md#登录与账号管理)。本次 GitHub 更新已获用户明确授权；今后的推送仍需用户确认。
