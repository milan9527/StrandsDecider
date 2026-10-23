# 已部署环境

最近发布日期：2026-10-23。

**访问地址：https://d3i7ogfx5ml7dc.cloudfront.net**

API 文档：https://d3i7ogfx5ml7dc.cloudfront.net/api/docs

**当前：文字 Decider 模块调用共享 vLLM / EC2 On-Demand `g6.xlarge`；图片决策调用另一台现有 `g6.xlarge` 上的官方视觉服务，两者持续运行。** 项目区域资源位于 `us-east-1`；CloudFront 和 IAM 为全球资源。Bedrock 使用美国跨区域推理配置。

**加密支付业务台：https://d3i7ogfx5ml7dc.cloudfront.net/#crypto**。演示路线、比较口径与实测结果见 [CRYPTO.md](CRYPTO.md)。

## 图片决策模块（2026-10-23，vision-v1）

- 新入口 [图片决策](https://d3i7ogfx5ml7dc.cloudfront.net/#vision)：支付状态、中文客服分流、凭证完整性，12 张预设图片及 PNG / JPEG / WebP 上传。显示实际问题、模型选择、概率和耗时，支持候选换序、无图及白图对照；实时结果与历史实测分别标识。
- 官方 v19 视觉服务部署在现有实例 `i-0daca64f56056aa1c` / `g6.xlarge` / L4，容器 `decider-vision-service-20261023-v1`，私网 `10.78.1.15:18123`。源码固定到 `d942e5515db750f80a51032629ec312455a87976`；离线依赖与模型缓存保存在磁盘，加载并预热后就绪，容器配置 `unless-stopped`。复用现有实例，没有新增 EC2。
- ECS API 通过 `DECIDER_VISION_URL` 调用视觉服务，安全组端口仅向业务 API 安全组开放。文字决策继续走共享 vLLM `172.31.33.164:8100`，健康检查分别确认 `official-vision` 与 `vllm`。
- API 镜像 `vision-20261023-v1`，ECR 摘要 `sha256:c325096f871c4e1b0d73156e45fd503a29c99f1644f98e978d5342442cc81ccd`，Task Definition **revision 23**。主 stack `UPDATE_COMPLETE`，ECS 滚动部署 `COMPLETED`；CloudFront invalidation `IAG1DN0XU18OULLXTL7GBHPIJH` 已完成，17 个前端与图片资源逐字节核对通过，S3 四项公共访问阻止及 OAC 保持启用。
- **256 项自动化测试通过**。线上 API 三次、浏览器五次实时调用均成功；浏览器验证三场景、换序／无图／白图、上传不套用样例预期、历史标识和 390px 布局，无 JavaScript 错误。五次浏览器调用中四次带图后端耗时为 **166.7–170.7 ms**，无图为 **142.1 ms**，仅作为接入验收记录。
- [模块说明](../docs/VISION.md)保留既有小样本实测及错误结果；新接入数据不替代先前基准。部署、API 和浏览器证据位于本机 `.deployment/vision-module/`，不含在公开仓库中。

## 全模块切换共享 vLLM（2026-10-16）

- 工作台、工具守卫、支付固定／优化流程、自主闭环、模型路由都通过同一个 `live_decision` 入口访问 vLLM，返回 `strands-decider-2B-hobson-v19-vllm`。业务输入、候选条件与执行保护保持原有逻辑；Jev 和 Bedrock 入口未改。
- 使用现有实例 **`i-0ae7eb0abcb815af3` / `g6.xlarge` / L4 / us-east-1d**。ECS 经已有 VPC Peering `pcx-056a4164043065e96` 调用 `172.31.33.164:8100/v1/systemone`，新增模型 IP 路由和两个 API 子网的回程路由，模型端口仅允许 API 安全组与原有 vLLM CloudFront VPC Origin 安全组。
- vLLM 密钥由 Secrets Manager 在 ECS Task 启动时注入 `DECIDER_API_KEY`，执行角色与新增单 AZ 私有端点限定到该密钥；浏览器不持有密钥。当前 `GPU_STATE_TABLE` 为空，不再获取原版 DynamoDB 独占推理租约；API 使用 128 个在途请求槽位，真实 vLLM 负责推理调度。
- `/api/health` 校验 `engine=vllm`，`/api/gpu` 显示共享实例和连接状态，`can_manage=false`。界面不启停共享实例，启停 API 返回 409；服务异常不影响登录和规则回放。
- API 镜像 `vllm-shared-20261016-v1`，摘要 `sha256:28a91953a5d1715951b5b0e0fc7c81aba9be4581b49d262c53de7466265b200f`；ECS Task Definition **revision 22**。主 stack `UPDATE_COMPLETE`，ECS 滚动部署 `COMPLETED`，原 revision 21 Task 已退出。
- 177 项相关自动化测试通过；包括原版兼容、vLLM 认证、三种协议、并发、上游限流、离线状态、支付与路由。新增真实接入验证保存 **83 次业务 API 响应**（含 5 次仅推进模拟事件的 tick），另外两次并发工作台请求均成功。固定／优化输入覆盖四场景共 40 次支付决策；四场景闭环分别用 6 / 6 / 9 / 6 次模型决策完成模拟业务。
- 浏览器四场景三模型原始路由验证：6 次预热另存，24 次正式调用全部成功；Decider 两步都返回 vLLM 模型 ID。桌面和 390px 手机端显示正确实例、无共享 GPU 启停按钮、无 JavaScript 错误。
- S3 四项公共访问阻止仍全开，匿名直连返回 403，未登录业务 API 返回 401；已核对发布前端与本地文件一致。README、当前 SVG 与部署／开发说明同步；历史原版测速、JevBench 和 PPT 数据保持原口径，本轮接入验证不是新的三模型性能基准。
- **迁移当日，原版实例 `i-0daca64f56056aa1c` 仍为 running，未停止、未删除磁盘，继续单独计费；文字演示不再调用它。** 2026-10-23 新增图片模块复用该实例，见本文顶部。共享 vLLM 实例也保持 running。原版启停方法归档至 [ORIGINAL_GPU.md](ORIGINAL_GPU.md)。
- 本机证据目录 `.deployment/vllm-migration-20261016/`：`live-verification.json`、`routing-browser/`、`gpu-browser.json`、`deployment-verification.json`、部署日志及更新前资源快照。GitHub 发布前完整回归为 243 项测试通过；凭据与本机部署证据不入库。

## 文档与 GitHub 同步（2026-10-12）

- README 以四场景三模型性能和业务结果为主，补充均值、中位数、成功次数、保护调整及两处选择差异；原双模型四场景表移入 [项目历史](../docs/HISTORY.md)，数据保持原值。
- [模型比较](../docs/MODEL_COMPARISON.md) 解释参考差异、实际动作与初始业务未完成；[Jev 指南](../docs/JEV.md) 对照官方 70–500 ms 端到端及高倍数宣传的条件，明确本批次 GPT / Jev 为 2.12×，没有纯 Jev 推理时间。
- 本次文档更新使用已采集数据，没有重新调用模型、部署 AWS 或启停 GPU。此前已部署的三模型代码、文档、SVG 和公开实测记录一并按用户授权提交 GitHub；PPT/PDF 保留原内容，提交以仓库记录为准。

## 统一三模型对比（2026-10-12，triple1）

- 支付流程固定为 **Strands Decider / Jev / GPT** 同时对比，移除配对选择器。四场景的固定流程、优化流程和自主闭环均使用三套独立结果及执行状态；桌面三列、手机纵向排列。每轮输入输出、步骤表、最终结果、客服记录和 JSON 导出包含三个模型。
- 每个模型保留自己的成功耗时、次数及错误。Jev、GPT 相对 Decider 的耗时倍数分别计算同输入成功配对，并显示有效步骤数；三模型均成功且输入相同才统计选择差异。闭环不显示固定输入耗时倍数，按各自全部成功调用计时。
- 首轮真实三模型测试在 USDC 受理阶段捕获 Jev `ConnectionClosedError`，该批 15 次调用中 14 次成功、1 次失败。其他两个模型仍完成模拟执行。随后改为每次 Jev 请求独立创建和关闭 Lambda SDK 客户端，读取完返回流后关闭连接，避免复用空闲连接及并发互相关闭连接；连接中断不自动重复提交模型请求。失败样本单独保留，未替换成回放。
- 199 项自动化测试通过；本地及线上四场景 × 三种方式的三模型规则回放通过。合成响应另验证第三模型单独选择不同、Jev 失败时其他模型继续执行、部分失败的合计与耗时倍数；公共 GPU 弹窗及 320–1440px 布局验证通过。
- 修复后的真实优化流程共 60 次调用全部成功，三个模型各 20 次。累计后端耗时分别为 Decider **2.157 秒**、Jev **9.143 秒**、GPT **19.423 秒**；与演示参考一致 **18/20、20/20、20/20**。每个场景仅测一次，计时包含各自部署与通信开销，不是通用准确率或纯模型推理速度。详见 [完整三模型记录](../docs/results/triple-2026-10-12.json)。
- API 镜像 `20261012-triple1`，摘要 `sha256:1d2b06ec20d8632841f627e5f5ff3c3706068c592c706086c060d72c63f878af`；ECS revision 14 完成滚动更新，主 stack 为 `UPDATE_COMPLETE`。前端版本 `triple1`，四个线上资源与本地逐字节一致，最终 CloudFront invalidation `IBTK161FANA3F1CKERD9XFSB96` 已完成。
- GPU 保持 `g6.xlarge` / `ready` / 常驻，本次未启停；S3 四项公共访问阻止开启、匿名访问 403，未登录业务 API 返回 401。README、Jev 指南、支付及闭环说明、四张 SVG 同步更新；PPT/PDF 未修改，GitHub 同步见本文顶部记录。
- 本地记录：`.deployment/triple-browser-local.json`、`.deployment/triple-browser-production-replay.json`、`.deployment/triple-browser-live-20261012.json`、`.deployment/triple-browser-live-20261012-first-failed.json`、`.deployment/triple-gpu-dialog-local.json`、`.deployment/triple-verified-20261012.json`。

## Jev 连接恢复与排查（2026-10-12，jev-connectfix1）

- 收到 Jev 失败反馈后，固定流程四场景及自主闭环接口复测均能返回真实结果，没有复现持续调用失败。此前部署日志存在 ECS 连接 Lambda 超时；由于缺少此次页面的具体错误，不能断定为同一原因。
- ECS → Lambda 仅在 TCP 连接超时、尚未提交请求时重连一次；两次失败明确提示「本步未提交模型请求」。读取超时返回 504，HTTP 错误、限流及可能已经提交的调用均不自动重试。启用 TCP keepalive，总等待上限为 50 秒。
- 增加不含密钥、业务输入或原始异常内容的错误日志，区分连接、读取、上游状态及响应格式。197 项自动化测试通过，包含重连恢复、两次连接失败、读取超时和上游错误不重复提交的回归。
- API 镜像 `20261012-jev-connectfix1`，摘要 `sha256:205e9ba68309ca876001db2b7697f0b6a3603778b3a57db342c457ef1d76e436`。ECS revision 13 完成滚动更新，旧任务退出；前端功能版本仍为 `jev1`。
- 新后端四场景 20 次 Jev 真实决策全部成功；浏览器 Jev / GPT 优化流程的五步对比、十个真实输出和两侧执行结果验证通过。记录见本地 `.deployment/jev-connectfix-verified.json`；独立网络诊断的十次新连接 DryRun 均成功，临时诊断任务已停止。
- 排查中的自主闭环观测单独保留：退款和结算完成；两个收款场景因 Jev 连续选择跟进而转人工，调用本身成功。没有用规则替换模型选择，也没有改写先前优化流程的实测表。
- 本次未启停 GPU、未轮换 Jev 密钥、未推送 GitHub。

## Jev 配对对比（2026-10-12，jev1）

- 支付流程对比新增「对比模型」选择：Decider / GPT、Decider / Jev、Jev / GPT。四场景均支持固定流程、优化流程和自主闭环，逐轮保留输入输出、实际模型版本、耗时、执行结果及历史组合；Jev / GPT 无需 Decider GPU。
- Jev 使用 Typesafe System One API，服务端别名 `jev-latest`，本批次实际版本 `jev-1.13.0`。输入问题及候选与同组模型一致；超时、限流、认证或格式失败明确显示，不替换为规则答案。
- 私有 ECS 通过单 AZ Lambda interface endpoint 调用 IAM 限定的转发函数 `strands-decider-demo-jev`，函数在 VPC 外访问固定 Jev HTTPS 地址。密钥由 Secrets Manager 保存，只有函数角色可读；前端、代码和实测导出不包含密钥。没有 Function URL，没有增加 NAT Gateway。配置、权限及新增计费项目见 [Jev 说明](../docs/JEV.md)。
- 192 项自动化测试通过；本地和线上分别验证两种新组合 × 四场景 × 三种测试方式，共 24 条规则回放流程，另验证错误分支、历史标识、JSON 导出及移动布局。原 Decider / GPT 固定、优化流程回归通过。
- 线上优化流程实测完成 80 次真实调用，全部成功。Decider / Jev 配对：累计后端耗时 1.558 / 5.674 秒，参考一致 18/20 / 20/20；Jev / GPT 配对：5.591 / 27.199 秒，参考一致均为 20/20。这是两组独立的单次观测，Jev 计时包含 Lambda 和 HTTPS 往返，不改写此前测速数据。完整结果见 [Jev 实测](../docs/results/jev-2026-10-12.json)。
- 新端点刚创建后，两次 API 冒烟请求出现连接超时；后续冒烟及上述 80 次实测成功。初期失败不计入成功实测批次，也未替换为回放结果。
- API 镜像 `20261012-jev1`，摘要 `sha256:f6e6c6146cb572afb16cc0d79fe1758fdaeef7f1fda06aa23d53aad121b5226e`；前端版本 `jev1`。主 stack 为 `UPDATE_COMPLETE`，CloudFront invalidation `I96ACEO3ORB64I1V1X1CFPMYZ4` 已完成，四个更新的线上前端资源与本地逐字节一致。
- GPU 保持 On-Demand `g6.xlarge` / `ready` / 持续运行，本次未启停 GPU。S3 四项公共访问阻止开启，匿名访问为 403；未登录访问业务 API 为 401。AWS 架构 SVG 已更新，已有 v6 PPT/PDF 保留原内容。
- 本地记录：`.deployment/jev-browser-live-20261012.json`、`.deployment/jev-browser-production-replay.json`、`.deployment/jev-original-regression.json`、`.deployment/jev-verified-20261012.json`。本次功能尚未推送 GitHub。

## 优化演示文稿与 GitHub 更新（2026-10-11，v6）

- 最新 [v6 PPT / PDF / 讲稿](../docs/presentations/v6/README.md) 在 v5 上增加两页，共 27 页：第 23 页展示 USDC 输入优化与真实审批输出，第 24 页比较四场景参考一致、耗时、保护调整及剩余错误。总结同步更新，Demo / Repo 入口保留于第 27 页。
- 保留第 14 页审批差异解释和删除重复来源页脚的修改。原 2026-10-10 测速记录不变，新增页单独使用 2026-10-11 EC2 的优化批次。输入优化没有改变模型权重，也不保证提速或选择完全正确。
- 截图来自已完成的真实模型测试及现网优化选项入口。仅矩形裁剪或直接截取界面元素，没有改写数值；本轮未重新调用模型、部署 AWS 或启停 GPU。
- 已核对 27 页 PPT/PDF、全部备注、数据与截图来源；渲染无缺字或页面越界，末页链接及两个二维码解析正确。新增页及总结页已完成目视检查，原 v5 PPT/PDF 保持不变。
- 相关 README、开发、部署、模型比较和闭环文档链接至 v6。经用户明确授权，将优化流程代码、真实观测、相关文档以及 v5/v6 演示更新一起提交 GitHub；版本以仓库提交记录为准。

## 四场景优化流程（2026-10-11，optimized1）

- 测试方式改为「固定流程 / 优化流程 / 自主闭环」，以优化流程替换原「仅比较决策」。四个场景均支持五步双模型判断和独立模拟执行；固定流程保留为基线。
- `input_profile=optimized` 按场景去除无关输入字段，明确候选适用的业务类型；不裁剪候选 ID、不注入参考答案、不改变资金与结案保护。两模型的业务输入、问题和候选条件一致；返回并展示真实 `model_input`，对比历史和 JSON 保留模式标签。切换模式后单独测试步骤会清除另一模式的旧结果。
- 171 项自动化测试通过，覆盖场景字段、候选集合、相同模型输入、基线兼容与保护校验。四场景双模式浏览器回放，以及固定流程、闭环、逐轮记录、失败恢复和移动布局回归通过。
- 线上真实验证完成 80 次模型调用，均成功：四场景 × 五步 × 两种输入 × 两模型。Decider 与演示参考一致的次数从基线 14/20 变为优化 18/20，保护调整从 4 次变为 1 次；GPT 两种输入均为 20/20。USDC 收款的 Decider 审批由等待人工审批变为规则检查通过；优化后仍保留少付核验、退款审批两项选择差异。
- 基线 / 优化累计后端耗时分别为：Decider 2.059 / 1.578 秒，GPT 18.694 / 23.174 秒。本次按场景先基线后优化，各执行一次，不能视作随机重复实验、通用准确率或稳定提速保证。完整输入、选择、概率、耗时及执行摘录见 [优化流程实测](../docs/results/optimized-2026-10-11.json)。
- API 镜像 `20261011-optimized1`，摘要 `sha256:7b92d92f1d16cf9b6912ea7f6c7465cd5c1b1af4cf6c852eaf12cadb75df864f`；前端资源版本 `optimized1`。ECS 滚动更新完成，CloudFront invalidation `I41TRD63DEK9GYBFMT6XV2IKFZ` 已完成；五个线上前端文件与本地逐字节一致。
- GPU 保持 EC2 `g6.xlarge` / `ready` / 持续运行，本次未启停 GPU。S3 匿名访问仍为 403，四项公共访问阻止均开启。
- 本地记录：`.deployment/optimized-browser-local.json`、`.deployment/optimized-browser-live-20261011.json`、`.deployment/optimized-verified-20261011.json`，以及 `optimized-*-regression.json`。代码、公开实测摘录与演示资料随本次 GitHub 更新提交，本地凭据和运行原始记录不入库。

## 演示资料与文档更新（2026-10-11，v5）

- [25 页 v5 EC2 部署版 PPTX / PDF / 讲稿](../docs/presentations/v5/README.md) 基于 v4 更新。第 9 页使用 AWS 图标重绘当前架构：私有 S3 + CloudFront OAC、内网 ALB、ECS Fargate API，以及私有 VPC 内的 EC2 `g6.xlarge` 常驻模型服务；后端直接调用模型、Bedrock 与 DynamoDB。
- 第 11 页更新 EC2 私网调用路径，备注同步 On-Demand、禁用闲置停机、磁盘缓存和费用。支付对比图表与截图保留 2026-10-10 的原始数据，并明确标注为迁移前历史实测；不将旧数据改标为 EC2 测速。
- 已验证 PPT/PDF 均为 25 页、25 页备注完整、原生文字无缺失或页面越界、历史数值与原始截图未改写、末页链接与渲染后的两个二维码可正确解析。10 份相关文档的本地链接检查通过，原 v4 文件哈希不变；结果见 [渲染检查](../docs/presentations/v5/render-audit.json)。
- 项目 README、部署、开发、模型对比、闭环与图表说明同步链接至 v5。原 v4 PPT/PDF 保留。演示资料更新没有重新部署 AWS、启停 GPU 或调用模型；经用户确认，连同此前 EC2 常驻与界面简化改动一并提交 GitHub，具体版本以仓库提交记录为准。

## 直接推理与顶部运行栏（2026-10-11，direct-run1）

- 常驻模式直接提交模型请求，取消每次运行前的 GPU 状态查询。初始化仍读取一次；GPU 弹窗打开或启停过渡期间才每 5 秒刷新，正常使用时不持续轮询。
- 真实 Decider 请求出现连接、超时或服务端错误后，异步检查 GPU；未就绪或状态不可用时打开恢复弹窗。参数校验、排队限流和 Bedrock 错误不触发 GPU 检查。保留手动启停和后端推理租约；历史闲置释放模式仍可使用启动前检查。
- 决策工作台顶部显示当前场景、问题数、运行模式和唯一的「运行决策」按钮；桌面与手机首屏可见，滚动时固定。「编辑输入」定位上下文，开始运行后定位结果，运行中按钮显示进度并禁用重复点击。
- 将「共享上下文：一次请求，多个独立判断」改为「共享上下文：同一份信息，多个独立问题」。当前逐项计时是一条浏览器 API 请求对应多次模型调用；独立问题不会自动接收前一问题的答案。
- 浏览器拦截测试覆盖 36 次正常模型请求，GPU 查询为 0；验证失败后检查、错误分类、过期管理状态不阻塞推理、弹窗权限与历史模式、320px 到 1440px 布局。完整工作台回归及 JavaScript / Prettier 检查通过，拦截测试仅使用明确的回放结果。
- 线上真实验证通过：工作台返回 3 个决策；支付固定流程完成 5 组真实双模型对话、10 个输出及对应模拟执行；运行期间 GPU 状态查询为 0，弹窗关闭后不轮询，390px / 320px 布局正常。GPU 保持 `ready` / `running`，未发起实例启停。
- 仅发布前端，API 仍为 `20261011-ec2always1`。线上 HTML、app.js、crypto.js、styles.css 已逐字节核对。最后一次文案发布的 CloudFront invalidation `IEZDSY7J38CMJ5P7FELJ3YXDMX` 已完成。
- 记录：`.deployment/direct-run-browser.json`、`.deployment/direct-run-gpu-dialog.json`、`.deployment/direct-run-regression.log`、`.deployment/direct-run-production-20261011.json`；截图位于 `artifacts/direct-run-production-*.png`。未推送 GitHub。

## EC2 On-Demand 常驻运行（2026-10-11）

- 新实例：`i-0daca64f56056aa1c`，`us-east-1d`，`g6.xlarge`，1× NVIDIA L4 / 24GB 标称显存，On-Demand，非 Spot，无公网 IP。ECS 模型服务通过私网 8099 端口供 API 调用。
- 原实例 `i-01bd22555b6f48d61` 在 `us-east-1f` 改为 `g6.xlarge` 后仍返回 `InsufficientInstanceCapacity`，因此转到另一可用区创建相同规格。原实例保持停止，80GB 加密磁盘保留；所有权标签改为 `DeciderGpuStack=strands-decider-demo-gpu-retained`，不参与当前控制器调度。
- 当前运行实例另有 80GB 加密 gp3 磁盘，缓存镜像、模型和编译结果。两块磁盘合计约 $12.80/月；GPU 计算费为 $0.8048/小时，730 小时约 $587.50，其他服务另计。
- GPU stack 参数：`ControllerState=ENABLED`、`GpuInstanceTypes=g6.xlarge`、`IdleTimeoutSeconds=0`。仅允许此规格，不因闲置停止，不因容量不足切到更贵机型；手动停止等待推理结束并保留磁盘。启动失败的 20 分钟超时保护仍有效。
- SageMaker Endpoint 不存在，SageMaker stack 参数 `ControllerState=DISABLED`；Model、EndpointConfig、ECR 镜像保留。共享状态表 `provider=ec2`，主 stack `ModelProvider=ec2`。
- API 镜像：`20261011-ec2always1`，摘要 `sha256:03fdf1da80f82d0c64eff9991399f0d4e0385ff739f79fe8d6a681567f8bf817`；模型继续使用已固定权重的 `20261009-gpu1`。
- GPU API 返回 `idle_auto_stop=false`、`idle_remaining_seconds=null`。公共管理弹窗与支付模块显示持续运行，保留手动停止入口。
- 160 项自动化测试通过，涵盖常驻模式不闲置停机、手动停止、启动失败保护、固定机型容量错误和已停止实例改规格；Ruff、JavaScript 语法及 CloudFormation 模板检查通过。
- 真实 CUDA 健康检查和四个支付场景的 20 组同输入配对决策、双侧模拟执行通过。Decider 累计后端耗时 1,651.831 ms（均值 82.59 ms），GPT 为 20,249.118 ms（均值 1,012.46 ms）；两侧各 20 次成功，无调用失败。这是本轮固定样本的观测，不是稳定延迟或通用准确率保证。
- 线上浏览器验证通过：EC2 常驻状态、手动停止入口、一次真实支付流程的五轮对话 / 十个模型输出 / 实际执行结果，以及 390px / 320px 布局。只执行观察与推理，验收后保持 GPU 运行。
- 部署核验通过：S3 匿名访问 403、四项公共访问阻止、CloudFront OAC、内网 ALB、无公网 IP 的健康 Fargate API、单台活动 On-Demand GPU、80GB 加密磁盘。CloudFront invalidation `I8E0IKN8EHZ5MPPLNA7S2H3QPU` 已完成，线上 HTML / app.js / crypto.js 与本地逐字节一致。
- 本机验收记录：`.deployment/ec2-g6-crypto-live-20261011.json`、`.deployment/ec2-g6-payment-browser-20261011.json`、`.deployment/ec2-g6-verified-20261011.json` 和 `.deployment/ec2-always-on-tests-20261011.log`。
- v5 演示 PPT 已同步当前 EC2 架构；历史性能图表仍对应采集时的 SageMaker 部署，未改写为 EC2 实测。代码和文档尚未推送 GitHub。

以下为此前功能与 SageMaker 部署的历史记录。

**2026-10-10 文档与演示材料更新**：[新版 34 页 PPT / PDF / 讲稿与最新截图](../docs/presentations/v2/README.md) 已按 `crypto10` 实现重做演示部分。复用已经就绪的 GPU 采集四个初始场景，得到 19 组成功同输入配对，另有 1 次 Bedrock 读取超时并保留错误；没有用回放替代真实输出。USDC 与退款两个自主闭环中，两模型均完成模拟业务。本次采集未发起 GPU 启停。原始摘录见 [固定输入](../docs/results/benchmark-2026-10-10.json) 与 [闭环](../docs/presentations/v2/loop-observations.json)。单次成功观测不代表通用准确率或稳定性能。

| 项目 | 2026-10-10 历史配置（当前状态见本文顶部） |
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
| ECR API repository / tag | `strands-decider-demo-api:20261010-loop1` |
| ECR model repository / tag | `strands-decider-demo-model:20261009-sm1` |
| 认证 | 自建用户名 / 密码，无 Cognito |
| DynamoDB 认证表 | `strands-decider-demo-auth` |
| 模型 | 官方 `StrandsAgents/strands-decider-2B-hobson-v19` |
| API 日志组 | `/ecs/strands-decider-demo` |
| 模型日志组 | `/aws/sagemaker/Endpoints/strands-decider-demo-decider` |
| Bedrock 对比模型 | `us.openai.gpt-6.1-sol`，GPT-6.1 Sol，推理强度 `low` |
| Bedrock Runtime 私网端点 | `vpce-0d5bced25d7fabac2`，`available`，单子网，Private DNS 开启 |
| 前端版本 | `crypto10`，独立业务模块 `/static/crypto.js` 和 `/static/crypto.css` |

## 显著展示每轮输入与输出（crypto10）

- 耗时卡片下方新增默认展开的「每轮输入 / 输出」，并排显示两侧请求的客户诉求、业务证据、模型选择、实际执行结果、时间与请求往返耗时。客服对话、模板回复及模拟交易按钮移到主区域，无需展开。
- 固定输入相同时共用一份输入展示；闭环按两侧各自轮次保留执行状态、上轮反馈与每次返回，模拟器事件明确标为未调用模型。请求失败保留输入与错误，继续运行追加新轮次，不覆盖失败记录。
- 每个案例保留最近 80 轮，可按对比批次回看和导出；证据修改后旧输入保持不变。原始业务请求、响应与执行尝试可逐轮展开；客服模板与模型决策分别标注。
- 本地已验证固定流程、四场景闭环、反馈传递、事件推进、失败恢复、输入快照不被改写、历史切换、JSON 导出、HTML 转义及移动布局；线上逐轮记录与公共 GPU 弹窗回归也通过。验证使用规则回放及明确注入的错误，未启动 GPU 或进行新模型测速。
- CloudFront invalidation `I8ZMSX7THYWTBPKM7FYCQAKAEO` 已完成，线上五个前端资源与本地逐字节一致。
- 前端独立发布，API 保持 `20261010-loop1`。核验记录：`.deployment/crypto10-verified-deployment.json`、`.deployment/crypto10-dialogue-production-browser.json`。

## 全模块 GPU 管理弹窗（crypto9）

- 决策工作台、工具调用守卫、支付流程对比、运行记录及说明页共用顶部「GPU」入口，实际启停按钮只保留在一个弹窗中。支付页的「GPU 管理」也打开同一窗口。
- 三个真实推理入口均在提交前读取 GPU 状态；未启动、启动中、停止中或状态未知时弹窗提示，不提交模型请求。示例／规则回放仍可使用。
- 管理员在弹窗中启动、停止或刷新状态；非管理员显示联系管理员提示。启动进度每 5 秒刷新，失败信息留在弹窗内，可重试。就绪后返回原模块重新运行，不自动续跑旧任务。
- 本地验证五个模块、真实推理拦截、重复点击、启动错误、推理失败后的状态刷新、停止、状态读取失败、非管理员、Escape／焦点返回，以及 320／390／768／1024px 布局；原工作台、固定流程与四场景自主闭环回放通过回归。
- 仅更新前端，API 保持 `20261010-loop1`。验证使用模拟 GPU 启停响应、截获的模型错误及真实规则回放接口，未启动计费 GPU；实际 SageMaker 仍为 `stopped / Absent`。
- CloudFront invalidation `I95PM0G6PLZJ1XT3ZV4RHCF14E` 已完成，线上 HTML、主脚本、支付模块脚本与两份样式文件均与本地逐字节一致。
- 发布核验与线上浏览器记录：`.deployment/crypto9-verified-deployment.json`、`.deployment/crypto9-gpu-production-browser.json`、`.deployment/crypto9-loop-production-browser.json`。

## 流程与速度对比排版（crypto8）

- 导航入口改为「支付流程对比」。顶部统一选择场景、测试方式及运行模式，只有一个「开始对比」入口；自主闭环作为测试方式选项，选中后才显示自动模拟证据开关。
- 主区域先显示两模型决策总耗时、耗时比和逐步建议／实际动作，再显示业务处理结果。输入、会话、完整执行记录、原始输出和日志按需展开。
- 支付页面隐藏全局 GPU 面板，使用测试设置内的一组控制；切回其他页面恢复原面板，避免重复启动按钮。
- 本地与线上固定流程、闭环回放、失败恢复、折叠状态、页面切换以及 320px／390px 布局验证通过。有耗时数值的排版另用明确标记的历史响应测试，未进行新的模型测速。
- 仅发布前端，API 保持 `20261010-loop1`。CloudFront invalidation `I748VJD0B2QF10R8P2CA1DE385` 已完成；线上四个前端资源逐字节一致，GPU 仍为 `stopped`。
- 验证记录：`.deployment/crypto8-verified-deployment.json`、`.deployment/crypto8-fixed-production-browser.json`、`.deployment/crypto8-loop-production-browser.json`。

## GPU 提示与自主闭环（crypto7）

- 固定输入对比改为「已对比的决策步骤」「两侧选择不同的步骤」，用具体步骤数解释分歧。闭环单独统计两侧返回的决策与耗时。
- 支付业务台显示 GPU 状态、管理员启动按钮和规则回放入口。真实运行前检查资源；未启动、启动中或状态读取失败时不提交决策请求。
- 新增「运行自主闭环」及自动模拟事件选项，每轮判断后执行并读取真实沙盒结果，再等待事件或重判。保留逐轮历史、错误记录、模拟器事件与结果；可暂停、继续和导出。
- 闭环最多 20 次返回决策，同一步连续两次无进展转人工；当前运行内资金步骤不会因结案重判再次执行。演练状态存于页面内存，尚不支持跨刷新恢复或生产数据库级幂等。
- API 镜像：`20261010-loop1`，摘要 `sha256:a516ea15812fa483ff14727dfbe3653755e21307b1dc524401e6d9804a2a4362`。CloudFront invalidation `I6DV2TH45A25PXGL4K97H5V0SR` 已完成，线上四个前端资源已逐字节核对。
- 156 项自动化测试通过；本地与线上浏览器验证四场景闭环、GPU 提示、手动事件续跑、失败恢复、账本去重、导出和手机布局；原固定输入流程回归也通过。测试使用规则回放及明确标记的错误分支，没有生成新的真实模型性能基准。线上记录为 `.deployment/crypto-loop-production-browser.json` 与 `.deployment/crypto7-fixed-production-browser.json`。
- 发布时实际 SageMaker 状态为 `stopped / Absent`；本次没有启动 GPU。实现与生产化边界见 [CLOSED_LOOP.md](../docs/CLOSED_LOOP.md)。

## 区分步骤处理与业务完成（crypto6）

- 最终卡片分别显示决策返回数、步骤处理数、模拟资金动作是否落实和业务完成状态。只有目标订单状态、对应账本记录和工单结案均确认，才显示业务完成。
- 待审批、资金挂起和未结案显示黄色待办状态；每步并列显示原始建议与实际采用动作，最终卡片列出未完成原因。JSON 导出新增 `businessOutcomes`。
- 前端发布于 2026-10-10；CloudFront invalidation `I7BMEQGJ1RZS294BHLKT9ODRF2` 已完成，四个线上资源已逐字节核对。API 镜像仍为 `20261009-crypto2`。
- 本地与线上浏览器已验证正常完成、模型保守选择导致两侧业务结果分歧、资金保护调整、失败重试、导出及手机布局。本轮使用规则回放和明确标记的错误选择测试，没有调用真实模型或启动 GPU；线上结果保存在 `.deployment/crypto-outcome-production-browser.json`。
- crypto6 使用固定输入决策后执行方案；crypto7 另加自主闭环，见 [CLOSED_LOOP.md](../docs/CLOSED_LOOP.md)。

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
- 2026-10-09 API 镜像摘要：`sha256:defe21c0a398747df17ae6dcdcd2920965c13f6ac0d548a2b5f3a5706b2b14e7`；最新版本见上方 crypto7 发布记录。
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

这些是 **EC2 历史结果，不能作为 SageMaker 性能结果**。随后原可用区出现 `InsufficientInstanceCapacity`，同一停止实例尝试 `g6.xlarge` 和 `g6.2xlarge` 仍无法启动。切换 SageMaker 时保留实例规格为 `g6.2xlarge`，处于停止状态，磁盘未删除；2026-10-11 的最新迁移见上文。保留磁盘不会预留 GPU 容量。

## 区域迁移历史

- 已将应用迁移到 `us-east-1`，管理员密码不变。
- 迁移时复制 9 个镜像版本并核对 ECR 摘要。
- 旧日志归档到 us-east-1 的 `/strands-decider-demo/migrated-us-east-2/ecs`、`gpu-controller`、`gpu-build` 日志组。
- us-east-2 的旧 stack、VPC、S3、ECR、认证表、日志和任务定义已删除，旧 CloudFront 地址失效。

本文件记录上述发布时点；实时状态以 CloudFormation、SageMaker 及 `.deployment/outputs.json`、`.deployment/sagemaker-outputs.json` 为准。

管理员用户名 `admin`；密码保存在本机 `.deployment/admin-credentials.json`，权限 0600，不写入文档、前端或镜像。账号管理见 [README.md](README.md#登录与账号管理)。本次 GitHub 更新已获用户明确授权；今后的推送仍需用户确认。
