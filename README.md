# Strands Decider · 决策实验室与加密支付业务台

一个可以实际操作的中文演示：让 **Strands Decider** 与 **Amazon Bedrock 上的 GPT-6.1 Sol** 判断同一笔业务，观察每一步的选择、耗时、执行结果和最终客服回复。

项目基于 [Strands Decider 官方介绍](https://strandsagents.com/blog/introducing-strands-decider/)，采用 FastAPI + 原生 HTML/CSS/JavaScript。AWS 部署使用私有 S3、CloudFront OAC、ECS Fargate 和 EC2 On-Demand GPU。

**[打开在线演示](https://d3i7ogfx5ml7dc.cloudfront.net) · [打开加密支付业务台](https://d3i7ogfx5ml7dc.cloudfront.net/#crypto) · [查看架构图](docs/diagrams/architecture.svg)**

**新版演示资料（2026-10-11，27 页 v6 优化流程实测版）：[PPTX](docs/presentations/v6/Strands-Decider-模型原理与支付业务演示-v6-优化流程实测版-27页-20261011.pptx) · [PDF](docs/presentations/v6/Strands-Decider-模型原理与支付业务演示-v6-优化流程实测版-27页-20261011.pdf) · [讲稿、截图与数据说明](docs/presentations/v6/README.md)。** 第 23–24 页新增输入优化方法、USDC 审批变化与四场景实测：Decider 与演示参考一致 14/20 → 18/20，仍保留两项错误和执行保护。包含真实界面截图；模型权重未变。保留 EC2 常驻架构、Jev / BERT 介绍和第 14 页审批解释。原 2026-10-10 观测与新增 EC2 优化批次分别注明来源，不混合统计。历史 [v5](docs/presentations/v5/README.md)、[v4](docs/presentations/v4/README.md)、[v3](docs/presentations/v3/README.md)、[v2](docs/presentations/v2/README.md) 保留。

在线演示需要现有用户名和密码登录，不使用 Cognito。账号密码、GitHub token 和模型权重不包含在仓库中。

## 1. 演示目的

本项目回答三个问题：

1. **小型专用决策模型能否承担 Agent / 业务系统中的高频判断？** 例如选择客服队列、核验下一步、决定继续跟进还是结案。
2. **同一个有限候选决策任务，Decider 与普通生成式大模型有什么差异？** 比较原始选择、参考一致情况、每步耗时、计费方式与接入流程。
3. **怎样把模型建议变成可解释的完整业务流程？** 分开显示模型原始建议、应用实际执行、资金保护调整和客户最终看到的结果。

| 工作区         | 功能                                                                                                                  |
| -------------- | --------------------------------------------------------------------------------------------------------------------- |
| 决策实验室     | 16 个场景、`choice` / `noul` / `score` 三种问题类型、可编辑上下文与选项、工具调用守卫、逐项计时、运行记录及 JSON 导出 |
| 加密支付业务台 | 四个支付案例 × 五个业务步骤，Decider / GPT 双侧对比，完整模拟订单、工单、账本与客服交互                               |

业务数据均为模拟快照。演示不连接钱包、不查询实时区块链、不广播交易。客服回复由应用模板根据实际处理结果生成，本次对比不测量自由长文本生成质量。

## 2. 架构与流程图

仓库包含四张 SVG 图，可直接在 GitHub 或浏览器中查看：

| 页面                     | 内容                                                   | 预览                                      |
| ------------------------ | ------------------------------------------------------ | ----------------------------------------- |
| 01 AWS 部署架构          | 网络边界、静态站点、API、两种模型、认证与 GPU 生命周期 | [SVG](docs/diagrams/architecture.svg)     |
| 02 Decider vs 普通大模型 | 相同输入、不同推理调用方式、输出校验、共同执行策略     | [SVG](docs/diagrams/model-comparison.svg) |
| 03 加密支付完整流程      | 五步流程、参考差异、保护调整、最终结果与模拟事件       | [SVG](docs/diagrams/payment-workflow.svg) |
| 04 自主闭环 | 两侧独立判断、执行、等待事件、反馈重判及停止条件 | [SVG](docs/diagrams/closed-loop.svg) |

部署架构图使用 **AWS 官方服务图标、官方配色及 Cloud / Region / VPC / 私有子网边界**。SVG 可直接下载用于演示材料，维护方式与图标来源见 [图表说明](docs/diagrams/README.md)；GitHub 不包含 `.drawio` 文件。

图中以后端直接连接 EC2 模型服务、Bedrock 和 DynamoDB 表示服务调用，省略私有网络端点节点；实际网络配置见下表。v6 PPT 沿用当前 EC2 架构；历史版本和测速数据保留其采集时的部署口径。

### AWS 部署

![AWS 部署架构](docs/diagrams/architecture.svg)

| 组件         | 当前实现                                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------------- |
| 前端         | 私有 S3 bucket，四项 Block Public Access 全部开启；CloudFront 通过 OAC 签名访问                             |
| API 入口     | CloudFront `/api/*` → VPC Origin → 内网 ALB → ECS Fargate                                                   |
| 业务后端     | FastAPI，1 个 ARM64 Fargate Task，0.25 vCPU / 0.5 GiB；无公网 IP                                            |
| 身份认证     | 自建用户名 / 密码；scrypt 密码摘要、可撤销 Cookie 会话、限流；AWS 用 DynamoDB，本地用 SQLite                |
| Decider      | 官方 `StrandsAgents/strands-decider-2B-hobson-v19`，ECS on EC2 `g6.xlarge`，NVIDIA L4 24GB / CUDA         |
| 普通大模型   | Bedrock Converse API，`us.openai.gpt-6.1-sol`，reasoning effort 为 `low`                                    |
| 模型网络     | API 经私网 HTTP 调用 EC2 模型服务；Bedrock 经私有 VPC endpoint 调用，权限限定到指定模型                      |
| GPU 控制     | On-Demand 常驻，禁用闲置停机；页面手动启停 → DynamoDB 状态与推理租约 → EventBridge / Lambda → EC2 Start / Stop |
| 业务演练状态 | 各案例、各模型的订单 / 工单 / 模拟账本保存在浏览器内存；刷新或退出清除                                      |

区域资源部署于 **us-east-1**，CloudFront 和 IAM 为全球服务。Bedrock 使用美国跨区域推理配置，AWS 可以将推理路由到其他美国区域。Decider 权重预置在镜像中；API 和 GPU 均无公网 IP，应用 VPC 无 Internet 默认路由。

GPU **持续运行，不因闲置自动停止**；只使用 `g6.xlarge`，容量不足也不自动升级规格。按需计算费 $0.8048/小时，730 小时约 $587.50/月；运行实例的 80GB gp3 磁盘约 $6.40/月，其他服务另计。手动停止会保留磁盘与模型缓存。旧可用区实例因容量不足保持停止，其另一块 80GB 磁盘暂留作回退（另约 $6.40/月）。SageMaker Endpoint 已释放，控制器禁用；Model 和 EndpointConfig 保留。

## 3. Decider 与普通大模型的流程对比

![模型调用流程对比](docs/diagrams/model-comparison.svg)

### 谁提供规则，谁做决定？

应用提供 **业务事实、问题、候选动作和各选项的适用条件**。Decider 在给定候选项中选择，返回原始选择、概率分布和 confidence。候选项不是 Decider 临时生成的。

普通大模型可以自由生成建议和文本，但本演示为了比较同一个任务，也向 GPT 提供相同候选项，并要求仅返回 `{"choice":"candidate_id"}`。两个模型收到相同的业务 payload，GPT 适配层另加输出格式要求。

Decider 的判断过程、confidence 含义，以及与常见 BERT 固定标签分类器的区别，见 [模型与参考策略说明](docs/MODEL_COMPARISON.md)。BERT 本身是深度学习模型，本项目未对 BERT 进行质量或性能实测。

| 维度               | Strands Decider                                       | Bedrock GPT-6.1 Sol                                     |
| ------------------ | ----------------------------------------------------- | ------------------------------------------------------- |
| 本次任务           | 有限候选动作选择                                      | 相同的有限候选动作选择                                  |
| 请求流程           | ECS API → 私网 HTTP → ECS on EC2 官方 System One 服务 | ECS → Bedrock Converse → 托管生成式模型                 |
| 输出处理           | 校验 `choice`、候选分布和 confidence                  | 解析生成的 JSON，校验唯一字段和候选 ID                  |
| 原始输出           | 选择、概率、confidence                                | 选择、输入 / 输出 tokens；不生成虚构概率                |
| 运行管理           | 自行部署 GPU 模型，当前常驻；支持手动停止并保留磁盘    | AWS 托管模型调用，受访问权限、限流和推理配置影响        |
| 成本口径           | 按 EC2 On-Demand 运行时间，另计磁盘与基础设施           | 按模型用量；页面记录 tokens，未核实单价时不估算美元金额 |
| 本演示未覆盖的能力 | 不承担自由长文本客服写作或自主交易                    | 未比较开放式规划、工具 Agent 循环、长文本生成质量       |

**固定输入对比的运行顺序：**

1. 冻结本轮业务快照。对每一个步骤，同时调用 Decider 和 GPT；五个决策步骤按顺序进行。
2. 收集两套五步建议，再分别执行各自的沙盒方案。两侧不共用已变更的订单或账本。
3. 原始建议与演示参考不一致时只显示提示，继续流程。
4. 资金条件不足时挂起资金动作，提前结案时改为持续跟进。记录原始动作、实际动作和保护调整原因，继续客服回复。
5. 模型或执行请求失败会明确显示错误，不用规则回放冒充真实模型输出。

以上描述的是固定输入模式。自主闭环模式则会读取每次实际执行结果，再继续判断。

结果区分别显示 **决策已返回、步骤已处理、模拟资金动作、业务完成**。挂起、等待审批和持续跟进也会计入已处理步骤，因此 `5/5` 不表示业务成功。只有模拟订单达到目标状态、存在对应收款／退款／对账账本记录且工单结案，才显示“业务已完成（模拟）”。未完成时列出外部条件、模型选择造成的待复核状态和保护调整原因；每一步并列显示原始建议与实际采用动作。JSON 导出中的 `businessOutcomes` 保留同样的判断和原因。

**自主闭环**：在顶部「测试方式」选择「自主闭环」，点击统一的「开始对比」，每步读取实际执行结果，再判断下一步。可勾选自动推进模拟确认、补款、地址验证、审批与结算；事件来源明确标记，风险需手动解除。关闭自动事件时等待手动推进，保留历史并续跑。每轮决策、实际动作和反馈完整展示；同一步连续两次无进展转人工，最多 20 次决策。当前运行保存在页面内存中，刷新会清除。实现与生产化边界见 [闭环工作流](docs/CLOSED_LOOP.md)。

**优化流程**：四个场景均可选择。以固定五步流程为基线，按场景去除无关输入字段，并明确每个候选适用的业务类型：收款不要求退款审批，退款保留地址与审批证据，结算使用到账与 SLA。两模型收到同一份优化后的业务输入、问题和候选条件，随后分别模拟执行。候选 ID 集合、演示参考及执行保护保持一致，不把参考答案输入模型，也不自动推进外部证据。可以先运行固定流程，再以相同证据运行优化流程，通过对比记录回看；模式、模型原始输入及结果随 JSON 导出。输入优化不保证模型总能正确选择。

2026-10-11 的 [四场景真实对比](docs/results/optimized-2026-10-11.json) 共 80 次调用均成功：Decider 与演示参考一致从 14/20 变为 18/20，GPT 均为 20/20；优化后仍有少付核验与退款审批两项差异。本次为每种输入各一次观测，不代表通用准确率。详细耗时及口径见 [支付演示说明](deployment/CRYPTO.md#优化流程optimized1)。

**对比界面**：顶部依次选择场景、测试方式（固定流程／优化流程／自主闭环）和真实模型／规则回放，再点击「开始对比」。耗时卡片下方默认展开「每轮输入 / 输出」及客户会话，逐轮并排显示输入证据、两模型建议、实际执行结果与时间；每轮可展开实际模型输入中的问题与候选条件。闭环每轮保留当时的执行状态及反馈；模拟器事件、失败请求、客服模板回复分别标记。可切换带模式标签的历史对比，最近 80 轮输入输出随 JSON 导出，证据更新不改写旧输入。流程总表与最终结果位于其后，证据编辑、原始 JSON 与日志按需展开。当前常驻模式直接调用模型，仅 Decider 调用失败后检查 GPU 并按需打开恢复弹窗；所有模块仍可手动打开顶部「GPU」管理入口。就绪后返回模块重新运行，不自动续跑；示例／规则回放无需 GPU。闭环耗时包含各自重判，不混入固定输入配对统计。

**决策工作台**：顶部运行栏集中显示当前场景、问题数、示例／真实模式和「运行决策」，桌面与手机首屏可见，向下滚动时保持固定。「编辑输入」定位到上下文，运行后自动定位到结果。

### 参考策略与执行约束

本演示的参考策略由开发者定义，供比较和教学使用，没有将其作为行业标准。默认的 **12 次链上确认、60 分钟结算 SLA** 也只是演示参数。

- **参考差异**：模型选择与 `reference()` 的参考动作不同，仅记录差异。
- **执行保护**：资金动作检查对应场景、到账金额、确认数、退款地址、人工审批、风险标记和待复核状态；结案还检查实际模拟订单状态。
- **保持真实**：后端保护调整不覆盖原始模型结果，也不计作模型判断正确。挂起资金后，客服回复不会声称已收款、已退款或已对账。

代码入口：[候选动作与条件](app/crypto.py)、[模型适配](app/bedrock.py)、[前端执行与结果展示](frontend/static/crypto.js)。

## 4. 场景演示

![加密支付五步流程](docs/diagrams/payment-workflow.svg)

五个业务步骤为：**客服受理 → 交易核验 → 风控审批 → 业务处置 → 回复结案**。

| 场景                    | 初始证据                                | 初始业务结果               | 推进方式                                           |
| ----------------------- | --------------------------------------- | -------------------------- | -------------------------------------------------- |
| USDC 已转账，订单未到账 | 应付 / 到账 129 USDC；确认数 3/12       | 资金待确认，工单持续跟进   | 点击「模拟确认数达标」，再运行完整流程             |
| USDT 少付               | 应付 100，到账 99.80 USDT；差额 0.20    | 等待补足，不能确认足额收款 | 点击「模拟补足差额」，重新核验                     |
| 稳定币退款              | 250 USDC；地址未验证、未审批            | 退款挂起，提示验证与审批   | 依次点击「模拟验证地址」「模拟审批通过」，重新运行 |
| 商户结算延迟            | 4,800 USDC；120 分钟未到账，SLA 60 分钟 | 升级或跟进结算工单         | 点击「模拟结算到账」，重新对账                     |

模型可能选择不同的保守处理路径，因此推进事件后仍应查看实际结果，不能把上述路线当作强制的模型答案。

### 推荐的 5 分钟演示路线

1. 登录并进入「支付流程对比」。首次体验可选择「规则回放」熟悉界面；回放不调用模型，不产生模型性能数据。
2. 确认页面显示 GPU 就绪，再切换到「真实模型」。当前 EC2 GPU 常驻；若已被手动停止，由管理员通过公共 GPU 弹窗启动。
3. 选择 **USDC 未到账**，测试方式选「固定流程」，点击「开始对比」。
4. 查看两侧五步原始选择、每一步的执行输出、耗时和最终客服回复。Decider 即使选择“等待人工审批”，也不会仅因参考差异停在 2/5。
5. 观察最终结果：可以显示 **已处理 5/5 步，同时资金动作未落实、业务未完成**。展开查看确认数、差额、审批或本次模型选择造成的阻塞原因；黄色状态表示仍有待办。
6. 点击「模拟确认数达标」，确认数从 **3/12 变为 12/12**。旧模型结果与执行状态会清除，重新运行观察变化。
7. 切换退款案例，先看地址未验证时的挂起路径，再模拟验证和审批。查看“原始模型建议”和“保护调整”是否不同。
8. 导出记录，复核本次输入、两侧结果、时间、参考差异、保护调整和模拟账本。

**「推进模拟交易」位于主区域「客户对话与回复」内，无需展开。** 点击事件后，会话立即显示系统通知、证据版本、时间与前后数值（如 `3/12 → 12/12`）；原有回复保留并标记为历史记录。模拟事件失败会显示原因且不改变证据。固定流程下需重新点击「开始对比」获得新回复；自主闭环等待中的事件会继续当前运行。

客户消息、金额、确认数、风险标记和结算耗时均可修改；修改后重新核验。详细操作与 API 行为见 [加密支付模块说明](deployment/CRYPTO.md)。

基础工作台另外提供客服分流、退款资格、销售线索、工具路由、RAG 依据、内容审核、发票校验、运维告警等 16 个场景，以及基于概率阈值的工具调用守卫，见 [开发与基础工作台指南](docs/DEVELOPMENT.md)。

## 5. 实测对比与计时口径

以下来自 **2026-10-10 12:26 UTC 开始**的线上真实采集，前端 `crypto10`、API `20261010-loop1`。四个初始场景每侧各尝试 20 次决策，得到 **19 组成功且输入相同的配对**；商户结算的 GPT 业务处置请求发生一次 `ReadTimeoutError`，保留错误并且未执行该侧不完整的方案。数据见 [benchmark-2026-10-10.json](docs/results/benchmark-2026-10-10.json)。

| 场景 | 成功配对 | Decider 合计 | GPT 合计 | Decider 参考一致 | GPT 参考一致 | 已处理步骤 D / G |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| USDC 未到账 | 5 | 458.3 ms | 7,791.8 ms | 4/5 | 5/5 | 5/5 · 5/5 |
| USDT 少付 | 5 | 452.5 ms | 5,469.0 ms | 4/5 | 5/5 | 5/5 · 5/5 |
| 稳定币退款 | 5 | 521.3 ms | 4,275.7 ms | 2/5 | 5/5 | 5/5 · 5/5 |
| 商户结算 | 4 | 377.4 ms | 4,531.6 ms | 3/4 | 4/4 | 5/5 · 0/5 |
| **合计** | **19** | **1,809.6 ms** | **22,068.2 ms** | **13/19** | **19/19** | **另有 1 次 GPT 请求失败** |

成功配对的 GPT / Decider 累计后端耗时比为 **12.20×**。这个比值不包含失败请求的等待时间，不能代表整次用户体验。Decider 的六次参考差异与四次执行保护调整均保留；初始条件下两侧均未完成资金业务。

**自主闭环另行观测：** USDC 未到账与退款两例均开启明确标记的自动模拟证据，两模型均完成对应订单、账本和工单结案。USDC 每侧返回 6 次决策、推进 1 个事件；退款每侧返回 9 次决策、推进 2 个事件。Decider 决策累计分别为 570.1 ms、897.3 ms；GPT 分别为 7,268.5 ms、10,542.0 ms。闭环后续输入可能不同，不将这些总时间混入固定输入配对统计；两例成功也不构成普遍完成保证。见 [闭环原始观测](docs/presentations/v2/loop-observations.json)。

历史 [2026-10-09 基准](docs/results/benchmark-2026-10-09.json) 保留供复核；旧批次的 8.87×、旧 PPT 另一批次的 7.49× 与本次结果不混算。

**如何解读：**

- 每步 `backend_total_ms` 包含后端到模型的通信、处理和排队，不能视为纯 GPU 计算时间。
- 同一步的两模型并发运行。表中的合计是各自五步时间之和，**不是浏览器整轮等待时间**，也不能将两列相加当作端到端延迟。
- 页面另外显示浏览器往返、五步决策经过时间、包含两侧沙盒执行的一键流程经过时间，以及沙盒请求往返合计。
- 只对同一输入指纹、真实成功的配对决策统计速度。失败、规则回放和输入不一致的数据不进入该统计。
- 参考一致率衡量与本演示自定义策略的相符程度，**不是通用准确率**；5/5 已处理既不代表五次判断都正确，也不代表资金业务完成。
- 这是固定案例上的一次观测，未测量多轮分布、P95 / P99、并发吞吐、冷启动和开放式任务，不能作为稳定性能保证。
- GPU 实例小时费与 Bedrock token 费用的计费基础不同。本项目没有足够依据声称哪一侧每次决策的美元成本更低。

以上历史样本在 SageMaker `ml.g6.xlarge` 上采集，当时计算参考价为 $1.1267/小时。2026-10-11 起改用 EC2 `g6.xlarge`，计算费 $0.8048/小时；API、ALB、PrivateLink、ECR 与磁盘另计，详见 [EC2 运维说明](deployment/README.md)。

## 6. 结论

1. **Decider 适合候选空间明确、需要低延迟的结构化判断。** 这次测试的累计后端耗时明显较低，但对本演示参考策略的吻合度也较低，必须保留可观察的输出与应用执行约束。
2. **普通大模型也能承担同样的选择任务。** GPT 在本次成功配对中全部符合参考策略，但耗时较高且另有一次请求超时；本演示未评估它在复杂解释、开放式规划与生成任务上的价值。
3. **业务系统应区分模型建议、参考答案和资金执行权限。** 保守建议不应仅因不同于参考答案就中断客服流程；资金挂起后仍可完成回复和跟进。
4. **固定的结构化条件可以直接写成代码。** 金额计算、交易状态核验和确定性的执行前置条件不必交给模型；模型更有价值的部分是理解自然语言、识别诉求并选择处理路径。

当前结果支持继续评估 Decider 在高频有限候选任务中的应用，不支持据此认定它可替代所有普通大模型，或直接承担真实支付执行。

## 7. 本地运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)；前端无需 Node.js 构建。

```bash
uv sync
uv run python -m scripts.manage_users create admin \
  --generate-to .deployment/local-credentials.json
AUTH_COOKIE_SECURE=false uv run uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

打开 `http://localhost:8000`，使用本机生成的凭据登录。基础工作台可以使用示例模式；进入 `/#crypto` 后选择「规则回放」即可体验完整业务流程。

真实 Decider 服务可在另一终端启动：

```bash
# 本地默认 CPU；NVIDIA 环境可使用 DECIDER_DEVICE=cuda
bash scripts/serve_model.sh
```

本地 API 如需调用真实 Bedrock，启动时设置 `BEDROCK_ENABLED=true`、`AWS_REGION=us-east-1`，并提供有该模型访问权限的 AWS 凭据。模型地址、超时、CPU / GPU 配置见 [.env.example](.env.example) 与 [本地开发指南](docs/DEVELOPMENT.md)。

## 8. AWS 部署与验证

当前部署使用 `us-east-1` 的 EC2 On-Demand `g6.xlarge` 常驻推理服务。初次部署和模型镜像步骤见 [部署入口](deployment/README.md)，实际资源及版本记录见 [DEPLOYED.md](deployment/DEPLOYED.md)。此前 SageMaker 方案见 [历史部署说明](deployment/SAGEMAKER.md)。

更新已有环境：

```bash
# 更新 API 和前端，保留现有 EC2 模型
python deployment/deploy.py --region us-east-1 --api-only \
  --model-provider ec2 --tag YOUR_NEW_API_TAG

# 仅更新前端
python deployment/deploy.py --region us-east-1 --frontend-only
```

本版本 **171 项自动化测试通过**。固定流程、优化输入、闭环回放、输入输出历史、公共 GPU 弹窗、异常恢复与移动端均有验证；2026-10-10 另完成真实固定输入及两场景闭环采集，2026-10-11 在 EC2 完成四场景共 20 组真实配对决策与模拟执行。回放与模拟错误测试不计入真实模型性能统计。复测命令：

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check app tests scripts deployment examples
node --check frontend/static/crypto.js

# 本地已启动服务时，验证完整页面与参考差异后的继续执行
uv run --with playwright playwright install chromium
uv run --with playwright python scripts/check_crypto_browser.py \
  --url http://localhost:8000 \
  --credentials .deployment/local-credentials.json

# 闭环与 GPU 提示（GPU 状态响应为测试模拟，不启动真实实例）
uv run --with playwright python scripts/check_crypto_loop_browser.py \
  --url http://localhost:8000 \
  --credentials .deployment/local-credentials.json

# 逐轮输入输出快照、历史切换、失败续跑、转义与手机布局
uv run --with playwright python scripts/check_crypto_dialogue_browser.py \
  --url http://localhost:8000 --credentials .deployment/local-credentials.json

# 全模块 GPU 公共弹窗；启停与模型调用均在浏览器内拦截
uv run --with playwright python scripts/check_gpu_dialog_browser.py \
  --url http://localhost:8000 --credentials .deployment/local-credentials.json

# AWS 环境：GPU 就绪后复测四个真实配对案例
uv run python scripts/check_crypto_models.py \
  --url https://d3i7ogfx5ml7dc.cloudfront.net \
  --credentials .deployment/admin-credentials.json \
  --output .deployment/crypto-models-rerun.json
```

浏览器验证添加 `--live` 可执行一次真实双模型完整流程。验证输出写入忽略的本地目录；仓库中的基准 JSON 仅保留不含凭据的实测摘录。

## 9. 项目结构与接口

```text
app/
  main.py                  # FastAPI、认证集成、原有决策接口与计时
  crypto.py                # 支付场景、演示参考、执行保护与回复模板
  crypto_profiles.py       # 优化输入：场景字段与候选适用条件
  crypto_loop.py           # 受限反馈闭环、等待、重判、预算与当前运行内账本保护
  bedrock.py               # GPT-6.1 Sol Converse 适配与输出校验
  sagemaker.py             # 签名的 SageMaker InvokeEndpoint
  auth.py                  # 自建账号、会话、限流
  gpu.py / gpu_state.py    # GPU 控制 API、状态与推理租约
frontend/
  static/crypto.js          # 两侧决策、完整沙盒执行、每步与最终结果
  static/crypto.css         # 支付工作台与移动端布局
deployment/                # CloudFormation、镜像、控制器、部署与运维
docs/
  diagrams/                # AWS 架构、模型对比、固定流程与反馈闭环 SVG 图
  presentations/v6/        # 最新 27 页优化实测版 PPTX / PDF、讲稿与截图
  presentations/v2/        # 历史实测截图、固定输入与闭环采集来源
  MODEL_COMPARISON.md      # 判断机制、BERT 区别、演示参考与执行约束
  CLOSED_LOOP.md           # 闭环实现、观测指标与生产化边界
  results/                 # 本次实测摘录
  DEVELOPMENT.md           # 本地模型、基础工作台、工具守卫与详细 API
scripts/                   # 账号管理、图表生成、浏览器与真实模型验证
tests/                     # API、认证、计时、GPU、SageMaker 与支付流程测试
```

| 接口                                                  | 用途                                              |
| ----------------------------------------------------- | ------------------------------------------------- |
| `/api/auth/login`、`/api/auth/me`、`/api/auth/logout` | 自建登录、会话查询与退出                          |
| `/api/examples`、`/api/decide`、`/api/guard`          | 基础场景、Decider 推理与工具调用守卫              |
| `/api/crypto/catalog`                                 | 支付案例、步骤与候选项                            |
| `/api/crypto/decision`                                | 单步骤、单模型决策或明确标记的规则回放            |
| `/api/crypto/apply`                                   | 顺序执行、参考差异提示、资金 / 结案保护与状态更新 |
| `/api/crypto/loop/tick`                               | 根据执行反馈单步推进自主闭环，等待事件、重判与预算控制 |
| `/api/crypto/event`                                   | 模拟确认、补款、地址验证、审批或结算到账          |
| `/api/gpu`、`/api/gpu/start`、`/api/gpu/stop`         | GPU 状态与管理员启停                              |

登录后可访问 `/api/docs`。业务 API 需要有效会话；写请求沿用 CSRF / Origin 校验。

模型版本、权重许可与推理实现以 [Strands Decider 官方仓库](https://github.com/strands-labs/strands-decider)为准。本项目是独立教学演示。
