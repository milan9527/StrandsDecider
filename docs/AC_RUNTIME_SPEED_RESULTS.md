# 空调控制运行时加速：保留完整输入的 Clef 与 Perplexity 实测

状态：本轮测试完成。测试日期：2026-10-31。

报告生成时间（UTC）：`2026-10-31T16:56:39.037977+00:00`。

本轮针对上一轮 token 压缩损害准确率的问题，保留原始问题与全部选项，实测能否通过减少重复计算、GPU 填充及结果传输来加速。范围为 Clef、Perplexity 的运行时优化；其他七种模型沿用已有结果，本轮没有重测。

## 结论

- **clef 的“完整输入，共享前缀计算”通过本轮全部门槛。** 原规范 20 题各三轮：完整任务平均 **15.187 → 5.068 秒**，快 **3.00 倍**。质量集严格正确数 **144/156 → 144/156**；完整质量验证及服务重启复测均未出现新增错误。
- **pplx：没有方案通过全部门槛，保留原始运行方式。**
- 普通独立字段批处理没有达到加速门槛；Clef 集中传输结果也没有可测的收益。
- “不降低准确率”指本轮冻结测试集上的对照结果，不代表已证明所有未来输入都不会退步。原版已有错误仍按错误计入。

## 与原测试规范的关系

遵循 [AC_Control_Test_Spec.md](../validation/ac_control/runs/2026-10-30-v1/spec.md)：每条查询携带完整 Command Set，只能返回明确要求且受支持的全部设置；摄氏/华氏温度必须包含单位伴随字段。保留 30 个字段、283 个候选（含每字段的 `omit`），未筛选候选、改写提示词、压缩 state、修复答案或改变评分。值 `0` 是实际指令，不能作为省略处理。标准答案始终只用于本机离线评分。

完整命令的准确率使用严格 `cmdKey/cmdValue` 集合匹配；多选一条、漏选一条均算整个任务错误。原规范 20 条分成 10 条单指令与 10 条多指令；单/多指令描述用户意图数量，单步/串行/一次全答描述调用方式，二者不是同一维度。

## 测试设计与计时

- 同一台 us-east-1d 的 g6.xlarge / L4；模型依次独占 GPU，不同任务始终串行。使用原有 BF16 权重，未量化或更改注意力方向。
- 筛选：S01、S03、S04、M08、M09、N03、N09、N10、H20、Z05 共 10 条混合指令；每方案预热一次，正式题轮换方案顺序。
- 完整质量验证：原规范 20 条、扩展诊断 10 条、英文验证 24 条、中文验证 24 条，合计 78 条查询；分别使用原序和倒序候选，共 156 个请求条件。
- 性能验证：原规范 20 条 × 3 轮，原版与候选交替。通过后重启服务，对 10 条筛选题以及完整验证中发生选择变化的条件各重复 3 次。
- 采用门槛：接口无异常；原先正确的任务不能变错；各数据集/候选顺序的准确率、多选和漏选不退步；完整任务平均耗时至少降低 10%，P95 不增加；重启后选择稳定。
- 完整验证一旦发现原先正确的任务变错，就在完整任务边界提前结束该淘汰方案；保留全部已执行回执，不重试，也不将未完成部分记为通过。
- 计时包含本机 HTTP 往返和 SDK 处理。加载、编译、预热、编码审计、写盘及上传均在正式计时之外；SDK 时间包含 CPU 与 GPU，不等于纯 GPU 时间。

| 调用布局 | 每个完整任务如何执行 | 时间含义 |
|---|---|---|
| 原始 30 步串行 | 30 次真实 HTTP 调用，每次一个字段 | 整轮实际墙钟；单步统计来自这些真实调用 |
| 独立字段批处理 | 同一任务的独立字段按 2/4/8 个一批，保留样本隔离 | 完成全部 30 字段的墙钟 |
| Clef 共享前缀 | 1 次 HTTP 提交 30 个独立样本；公共前缀一次计算，各字段后缀依次计算 | 完成同一任务全部 30 字段的墙钟；不是单字段延迟 |
| 原生一次全答 | 1 个样本同时包含 30 个问题，由官方联合模型处理 | 独立比较的原生布局，不能替代串行布局的准确率基线 |
| Perplexity 缩小填充桶 | 仍是 30 次真实单字段 HTTP 调用，只改变 CUDA 图填充长度 | 与原始 30 步串行直接配对 |

## 筛选结果

以下准确率分母为 **10 条混合筛选题**，不是原规范 20 题的分母。百分比变化均与同一阶段对应基线比较。

| 模型/阶段 | 方案 | 严格正确 | 平均完整任务 | P95 | 新增错误任务 | 耗时变化 | 筛选通过 |
|---|---|---:|---:|---:|---:|---:|---|
| clef/screen | 原始 30 步串行 | 8/10 | 15.078 秒 | 15.324 秒 | — | — | 对照 |
| clef/screen | 独立字段 2 题/批 | 8/10 | 16.564 秒 | 16.815 秒 | 0 | +9.9% | 否 |
| clef/screen | 独立字段 4 题/批 | 8/10 | 17.595 秒 | 17.874 秒 | 0 | +16.7% | 否 |
| clef/screen | 独立字段 8 题/批 | 8/10 | 20.554 秒 | 20.773 秒 | 0 | +36.3% | 否 |
| clef/screen | 原生一次全答 | 5/10 | 3.387 秒 | 3.433 秒 | — | — | 对照 |
| clef/screen | 全答：集中结果传输 | 5/10 | 3.387 秒 | 3.434 秒 | 0 | +0.0% | 否 |
| clef/sorted-screen | 原始 30 步串行 | 8/10 | 15.080 秒 | 15.284 秒 | — | — | 对照 |
| clef/sorted-screen | 按长度排序，8 题/批 | 8/10 | 18.578 秒 | 18.820 秒 | 0 | +23.2% | 否 |
| clef/prefix-screen | 原始 30 步串行 | 8/10 | 15.199 秒 | 15.343 秒 | — | — | 对照 |
| clef/prefix-screen | 完整输入，共享前缀计算 | 8/10 | 5.099 秒 | 5.174 秒 | 0 | -66.5% | 是 |
| pplx/screen | 原始 30 步串行 | 8/10 | 11.099 秒 | 11.169 秒 | — | — | 对照 |
| pplx/screen | 独立字段 2 题/批 | 7/10 | 11.024 秒 | 11.097 秒 | 1 | -0.7% | 否 |
| pplx/screen | 独立字段 4 题/批 | 7/10 | 11.379 秒 | 11.531 秒 | 1 | +2.5% | 否 |
| pplx/screen | 独立字段 8 题/批 | 7/10 | 11.962 秒 | 12.031 秒 | 1 | +7.8% | 否 |
| pplx/tight-screen | 原始 30 步串行 | 8/10 | 11.076 秒 | 11.357 秒 | — | — | 对照 |
| pplx/tight-screen | 30 步串行，缩小图填充桶 | 7/10 | 8.659 秒 | 8.851 秒 | 1 | -21.8% | 否 |

集中传输只与 `full_original` 比较；其他优化与同阶段 `serial30` 比较。

## 完整验证与重启复测

### clef

完整验证状态：`complete`；已记录 434/434 个任务块（包含预热及两种布局）。

`prefix30`：已配对 216 个正式任务；新增错误 0 个，选择变化 0 个；报告概率的最大绝对差 0.0260。

| 质量分组 | 原始严格正确 | 候选严格正确 | 原始多选/漏选 | 候选多选/漏选 |
|---|---:|---:|---:|---:|
| spec/original/prefix30 | 20/20 | 20/20 | 0/0 | 0/0 |
| spec/reversed/prefix30 | 20/20 | 20/20 | 0/0 | 0/0 |
| extension/original/prefix30 | 9/10 | 9/10 | 1/0 | 1/0 |
| extension/reversed/prefix30 | 9/10 | 9/10 | 1/0 | 1/0 |
| validation/original/prefix30 | 22/24 | 22/24 | 3/0 | 3/0 |
| validation/reversed/prefix30 | 22/24 | 22/24 | 3/0 | 3/0 |
| chinese/original/prefix30 | 21/24 | 21/24 | 4/0 | 4/0 |
| chinese/reversed/prefix30 | 21/24 | 21/24 | 4/0 | 4/0 |

原规范性能对照（20 题 × 3 轮；候选 `prefix30`）：

| 布局 | 严格正确 | 平均完整任务 | P95 完整任务 | 实测单字段平均 / P95 |
|---|---:|---:|---:|---:|
| 原始 30 步串行 | 60/60 | 15.187 秒 | 15.323 秒 | 506.1 / 645.1 ms |
| 完整输入，共享前缀计算 | 60/60 | 5.068 秒 | 5.153 秒 | 不适用：返回完整任务 |

重启复测 `prefix30`：通过；混合场景严格正确数 24/30 → 24/30；选择漂移 0，新增错误 0；平均加速 3.00 倍。

- pplx：候选未通过筛选，未进入完整验证。

## 为什么有的方案有效，有的无效

### Clef：复用完全相同的前缀计算

官方编码先放 state，再放当前字段的问题和候选。30 个独立字段的开头大量相同。实验先找逐 token 完全相同的前缀，在原生 GDN 的 64-token 边界切开，仅预计算一次。随后为每个字段独立复制可变的 KV、卷积及循环状态缓存，处理该字段的完整后缀，再拼回完整隐藏状态，交给原封不动的官方决策头评分。各字段没有共享其他字段的续接状态。

筛选中，原始逻辑输入累计约 43,673 token/任务，优化后保持相同；主干实际处理的位置累计从约 43,673 降到 10,265，减少约 76.5%。每个任务新建前缀缓存，任务之间不复用答案。决策头仍读取完整隐藏序列，因此减少的位置数不能直接当成总 FLOP 的减少比例。本方案降低自托管 GPU 的重复计算量，接口报告的逻辑输入 token 数不变。

完整质量集 156 个条件的结果同样成立：每任务逻辑输入平均 43,637 token，主干实际处理 10,229 个位置，减少 76.56%。[完整计算量记录](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-confirmation-token-accounting.json)

这种拆分保留因果计算语义，但可能改变 BF16 数值路径；筛选中概率最大绝对差为 0.026。不能只凭“输入没变”就宣称选择必然一致，必须经过完整质量和重启验证。

### Clef：普通 batch 与结果传输

官方 `collate_records` 将独立样本补齐到批内最长序列。2/4/8 题一批的填充位置分别增加约 7.4%/14.0%/32.1%；按长度排序后 8 题一批仍增加约 19.5%，实测仍更慢。本轮长输入在 L4 上没有获得足以抵消额外计算的批处理收益。原始串行 SDK 平均约 15.044 秒、整任务约 15.078 秒，HTTP 等外部开销很小；减少调用次数本身不能解释前缀方案的大幅加速。

全答传输优化仅将逐字段 softmax 结果集中拷回 CPU，筛选输出完全相同，但耗时约 3.387 秒，几乎没有变化。这个原生全答布局在筛选中只有 5/10 正确，而串行及前缀布局为 8/10，不能为了更短时间直接替换。

### Perplexity：独立批处理与 GPU 填充

使用官方 `Decider.decide(list_of_requests)` 的独立序列处理路径，2 题/批只快约 0.7%，4/8 题反而更慢，并且三种批量都让 M08 新增错误。该查询是 `Turn on up-and-down swing and set the horizontal airflow to both sides.`，只要求 `t_up_down=1` 和 `t_swing_direction=2`：原串行对 `t_swing_angle` 选择 `omit`；批处理却选择 `0`，增加一条未请求的垂直风向命令。原串行的 `omit` 与 `0` 概率恰好同为约 49.02%，官方选择函数在平分时取顺序靠前者；2 题/批时变成约 45.07% 与 52.94%，最终选了 `0`。这表明该题原本就处在决策边界，GPU 计算布局改变带来的数值差异足以改变答案。即使总准确率不变，也必须检查这种逐题退步。

另一个候选只缩小 CUDA 图填充桶：原桶为 2048/4096/8192/16384，候选为 1536/2048/2560/3072/4096。模型与真实输入不变；筛选输入长度为 1264–2351，图执行位置从每任务 63,488 降到 48,128，减少约 24.2%。这是减少填充计算，不是删除用户信息；仍需通过逐任务准确率门槛。

实际筛选：11.076 → 8.659 秒，耗时减少 21.82%，但严格正确数 8/10 → 7/10。M08 新增 `t_swing_angle=0`，因此淘汰。Z05 的一个多选字段有所改善，但整题仍错；两种方式的多选命令总数同为 4，不能用这个总数相等来宣称准确率不变。

## 可复查证据与边界

[冻结计划](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/plan.json) · [原始输入](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/cases.json) · [模型版本](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/models.json) · [提前淘汰规则](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/confirmation-early-stop-amendment.json)

| 模型/阶段 | 汇总 | 逐题评分 | 原始回执 |
|---|---|---|---|
| clef/screen | [汇总](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-screen-summary.json) | [评分](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-screen-scored.json) | [回执](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/results/clef/screen/tasks.jsonl) |
| clef/sorted-screen | [汇总](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-sorted-screen-summary.json) | [评分](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-sorted-screen-scored.json) | [回执](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/results/clef/sorted-screen/tasks.jsonl) |
| clef/prefix-screen | [汇总](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-prefix-screen-summary.json) | [评分](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-prefix-screen-scored.json) | [回执](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/results/clef/prefix-screen/tasks.jsonl) |
| clef/confirmation | [汇总](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-confirmation-summary.json) | [评分](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-confirmation-scored.json) | [回执](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/results/clef/confirmation/tasks.jsonl) |
| clef/repeatability | [汇总](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-repeatability-summary.json) | [评分](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-repeatability-scored.json) | [回执](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/results/clef/repeatability/tasks.jsonl) |
| pplx/screen | [汇总](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/pplx-screen-summary.json) | [评分](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/pplx-screen-scored.json) | [回执](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/results/pplx/screen/tasks.jsonl) |
| pplx/tight-screen | [汇总](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/pplx-tight-screen-summary.json) | [评分](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/pplx-tight-screen-scored.json) | [回执](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/results/pplx/tight-screen/tasks.jsonl) |

[clef 最终采用判定](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/clef-decision.json)（初筛 selection 文件保留当时的待验证状态，最终结论以 decision 文件为准）。

[pplx 最终采用判定](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/pplx-decision.json)（初筛 selection 文件保留当时的待验证状态，最终结论以 decision 文件为准）。

审计通过：共 10,339 次实际推理 HTTP 调用（含预热），接口异常 0 次，请求重叠 0 次；99 个 README 的哈希保持不变。[审计记录](../validation/ac_control/runs/2026-10-31-clef-pplx-runtime-speed-v1/audit.json)

单步延迟只取真实单字段调用；不能用完整任务耗时除以 30 充当单步响应时间。20 题三轮的正确数是重复观测数，独立查询仍是 20 条。本轮不同模型的软件环境各沿用原有版本，结果用于各自优化前后比较，不据此重新排名全部九模型。

优化通过隔离实验验证，尚未部署到生产。README 不在本次报告发布范围内，EC2 按用户要求保持运行。计划和审计记录中的 GitHub 状态保留测试结束时的记录；本报告及所引用结果随后按用户要求发布。
