# 空调控制的其他开放权重决策模型

调研与测试日期：2026-10-30。依据当前 JevBench 页面、候选模型固定版本的官方文档与本项目已有测试。已使用用户授权新增的一台 g6.xlarge，完成四个新候选与 H2O 的同机对照。[规范 20 题主报告](AC_SPEC_UNIFIED_RESULTS.md)加入 Jev/GPT 同方式补测；[部署与扩展记录](AC_CANDIDATE_L4_RESULTS.md)保留运行条件及补充观察。

**以 `AC_Control_Test_Spec.md` 为准：本轮本地候选中 Clef 准确率最高，KnowLine 完整请求最快。** 规范原序 20 题中 Clef **19/20**，KnowLine、H2O、Torchcast 均 **18/20**，Perplexity **1/20**；20 条完整请求均值依次为 **3.241 / 1.046 / 6.154 / 12.482 / 1.483 秒**。低延迟优先继续评估 KnowLine；规范准确率优先继续评估 Clef，同时保留逐题多发动作的缺陷。

扩展集另行观察：H2O 为 144/156、KnowLine 137/156，中文指令两者均 46/48。这只能说明该扩展范围中的结果，不能替代规范 20 题排名，也不能与固定 S03 的计时混作主指标。

下面保留实测前的选型依据与官方文档分析：Perplexity 用于验证多字段共享计算，KnowLine 验证中文指令，Torchcast 验证通用决策能力能否迁移，Clef 验证联合字段评分及作者家电任务证据。实际结果说明，榜单几十毫秒与作者家电成绩均不能直接替代本地完整空调测试。中文分项仅翻译用户指令，规则与能力表仍沿用英文协议。

四个优先候选的固定版本模型卡均标注 Apache-2.0。下文的大模型备选分别说明 MIT、非商用或专用社区许可，避免把“开放权重”统一视为同一种使用许可。

## 1. JevBench 提供了什么证据

来源：[当前开放权重榜单](https://benchmarkheaven.com/jev-models)、[方法说明](https://benchmarkheaven.com/jev-models/methodology)。下表摘自 2026-10-30 获取的实时页面，数值保留一位小数；p50 是页面明确标注的自托管实测值。

| 模型 | 参数规模 | Intelligence | Capability | 榜单实测 p50 |
| --- | --- | ---: | ---: | ---: |
| Torchcast Decision 4B v1.3 | 4B | 67.1 | 77.5 | 34 ms |
| H2O-Lightning-4B **v1.1，榜单参照** | 4B | 60.0 | 75.0 | 31 ms |
| baselabs elephant-1 | 9B | 55.8 | 70.2 | 75 ms |
| vLLM-SR d3-mini | 4.54B | 50.8 | 68.8 | 28 ms |
| KnowLine-4B-Gen5.5 | 4B | 46.4 | 66.2 | 30 ms |
| Cloudflare Clef-Flash | 9B | 42.2 | 63.8 | 104 ms |
| Perplexity Decider Flash v1.2 | 约 4.5B | 45.5 | 61.7 | 44 ms |

这里有四个必须保留的口径：

- **Intelligence 不是正确率百分比**，它包含机会水平修正、任务层级加权和公开/封闭集差距调整。Capability 是 Intelligence 与 Calibration 的平均值，不能理解为“整条空调命令正确率”。
- 页面标注每个自托管系统 1,500 个决策，但不同条目存在不同抽样批次。当前页面使用 v1.7 的每决策 10 秒失败规则，也已经显示 v1.8 的成本更新。页面链接的旧 `/api/jevbench/v1.6.1` JSON 仍是历史结果，**本表没有用它替代实时页面**。
- 自托管 p50 是榜单测量环境的 loopback 耗时；用于榜单速度轴/门槛的 `2 × 实测 + 150 ms` 是估算。它既不是我们的 L4 实测，也不是 30 字段总耗时，更不能直接与 Jev 云端网络时间比较。
- 榜单上这一行 H2O 是 **v1.1**。本项目部署基于 **v1.4.1** 的固定版本，因此只能把这行当作历史版本参照。不能据此断言 Torchcast 一定胜过正在优化的 H2O。

另外，模型卡里的 **Jev Decision Index 0.3/0.4** 与这里 Benchmark Heaven 的 **JevBench** 是不同评测；作者自己的公开集、家电模拟器结果也分别注明来源，不拼成一张“统一准确率”表。

## 2. 入选的三个 4B 模型

### Perplexity Decider Flash v1.2：优先验证完整多字段请求

[官方模型卡](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2/blob/9ff7cf9838e59df461c276b7699d56b244d2af58/README.md)说明：

- 一个请求的所有问题共享一条序列，在每个问题的标记位置读取答案；各问题可以互相看到。这与“30 个字段各自重新读取完整状态”的实现有实质区别。
- 每题支持 **1–255 个选项**；问题数量没有固定上限，受序列长度限制。可以覆盖我们的 30 字段和最多 102 个候选。
- `fast=True` 使用无填充打包、编译和 CUDA graphs；需安装官方快速内核并预热。
- 作者的 Decision Index 自测中，**家电模拟器联合提问比逐题提问高 3.4 分**。但其总体公开集是逐题 60.05、联合 58.88；联合提问对某些工具任务反而明显变差。不能把家电局部收益外推到所有任务。
- 超长请求会拆分问题并保留完整状态，单题仍放不下则报错，不截断。快速路径和 BF16 批次形状可造成少量临界选项翻转。

**本项目已有证据：**10 月 29 日的简化设备任务，严格动作 16/24、最终状态 18/24，三字段请求 p50 247.6 ms；使用的是官方 `fast=False` 参考路径。它的正确率尚无明显优势，但快速路径与联合问题架构值得在完整 AC 协议上验证。

**定位：**优先做“30 字段总延迟”的候选，不能仅凭 `Flash` 名称认定更快。BF16 权重约需 9 GiB，另需工作显存；当前三个模型共驻的 L4 无法直接再加一个实例。

### KnowLine-4B-Gen5.5：优先验证中文与最终设备状态

[官方模型卡](https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5/blob/779944d2cc8ffa19cef386aee83c83bcb967ade2/README.md)、[推理说明](https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5/blob/779944d2cc8ffa19cef386aee83c83bcb967ade2/INFERENCE.md)说明：

- 明确支持英文、简体中文和繁体中文。最多 **64 个问题、每题 255 个选项**。
- 官方推荐 **SGLang 0.5.21 + FP8 + 前端**；HF BF16 是备用路径，没有 prefix cache。
- **每个问题一次前向计算**，并非 30 个问题只算一次。Gen5.5 对不超过 3,000 token 的文本题重复输入后读答案；权重与 Gen5 相同。
- 作者在一张 H20 上逐请求测得官方路径 p50 42.1 ms；HF 备用路径另一个小样本为 264 ms。样本和 GPU 都不同于我们，不可直接计算 L4 的加速倍数。
- 重读增加成本：作者全套测试输入 token 为 Gen5 的约 1.56 倍，且没有处处提升。

**本项目已有证据：**简化设备任务严格动作 **19/24**、最终状态 **23/24**，是那轮五个开放权重模型中最好的设备结果；三字段 p50 **851.7 ms**。当时是 HF BF16 + read-twice，没有使用推荐的 SGLang FP8。

**定位：**最有本地设备效果依据的准确率候选。先复现官方部署，再测完整 30 字段；不能由其 JevBench 较低总分直接否定中文设备任务，也不能把 23/24 当作完整空调规范成绩。

### Torchcast Decision 4B v1.3：优先验证通用能力能否迁移

[固定版本模型卡](https://huggingface.co/torchcast-ai/torchcast-decision-4b/blob/492bfb19662f3c6e601cc9c4bd2911ac95609ed4/README.md)、[官方部署说明](https://github.com/Torchcast-AI/torchcast-decision-4b/tree/v1.3.1)说明：

- 当前 JevBench 上，同为 4B，其 Intelligence/Capability 有吸引力。文档所称“开放模型第 1”指当时的 **Composite 排名**，不是 Capability 排名，更不是空调正确率第一。
- v1.3.1 是服务代码更新；作者声明与榜单测量的 v1.3.0 权重相同。需使用专用非因果注意力服务，普通 causal vLLM 不能复现。
- **超过 26 个选项采用分组初选和终选。**源码会让各组选出的候选进入最后一轮；原请求可以保留全部候选，但最终一轮并非对原始 102 项一起评分，应单独标记这种算法差异并检查换序影响。
- 源码的 CUDA graph 快速路径只覆盖 **1–4 个问题**：单题最长 4,096 token，多题每题最长 1,024 token；其他情况走 eager/分块计算。**30 字段任务不能直接套用其 34 ms 榜单值。**
- 文档将预期用途限定为英文文本决策研究；中文控制语义需要专项测试。默认对超过 16,384 token 的状态保留头尾，测试必须确认实际输入未被截断。

**定位：**最值得新增的 4B 通用能力对照，但其多字段路径和大候选集合是明确的部署/算法边界。权重与当前服务代码为 Apache-2.0；早期 v1.1 的非商用许可不能混用。

## 3. Clef 与其他备选模型

### Cloudflare Clef-Flash 9B：与任务结构最贴近

[官方模型卡](https://huggingface.co/Cloudflare/clef-flash/blob/f0b7d3cd65296abfe459e6c228b618f5d8b26d2f/README.md)说明它使用联合 schema head，**一次前向计算对所有问题的所有选项评分**，提供 Jev/SystemOne 接口。作者在 Decision Index 0.2.1 的内部复测中报告：

| 家电模拟任务，case exact accuracy | Clef-Flash | Clef | 该次对照 Jev |
| --- | ---: | ---: | ---: |
| 作者自测 | 97.7% | 83.0% | 52.3% |

这是最贴近本项目任务的公开证据之一，但仍是**不同数据集的作者自测**。不能理解为它在我们的中文 30 字段测试有 97.7%，也不能将表中的 Jev 当作本项目 Jev 1.14 的同条件成绩。JevBench 中 Clef-Flash 的 Intelligence 只有 42.2，也提示需要检查泛化而非只看家电单项。

官方提供 SGLang 专用服务，文档验证硬件为 H200 等；9B 的 BF16 权重本身约需 18 GB，再加工作内存。当前共驻 L4 不适合直接增加它，独占 L4 能否容纳完整负载也应测峰值后再判断。

代码还有一个需要实测记录的边界：默认总长 16,384 token，schema 优先保留，超限时会裁切状态。接入本测试时应在发送前检查长度，确保没有丢失用户指令或能力说明。

### baselabs elephant-1 9B：共享输入计算的备选

[官方文档](https://huggingface.co/baselabs/elephant-1)给出 shared-prefix prefill、多问题概率输出、16,384 token 上限及专用 OneJev + patch 运行时，权重为 MIT。它的 JevBench Intelligence 55.8、Capability 70.2，支持保留为 9B 备选；本次没有找到与 Clef-Flash 同等直接的空调实测证据，因此排在其后。其文档中的 Decision Index 62.65 是另一套榜单的历史结果。

### vLLM-SR d3-mini：部署对照，而非首选准确率升级

[官方文档](https://huggingface.co/vllm-sr/d3-mini/blob/bd0090dd758d32ba59ef5c749910a8e87fc4391f/README.md)有较完整的多问题测试与部署说明，Apache-2.0、255 选项，支持图片和视频。但官方明确 **每个问题分别前向计算**，一个 API 调用不等于一次模型计算。

作者在 MI325X 上测得 AutoModel 单题 18.1 ms、16 题 115 ms；这些都是作者硬件与短输入结果。其 Engine 模式单副本峰值显存记录在 19.5–21.9 GiB，自动模型路径约 14.8 GiB；并非 L4 保证值。批处理还有少量临界答案变化。对当前纯文本空调任务，它更适合做服务实现的对照，暂不优先于上面的三个 4B 候选。

## 4. 为什么不直接选榜首大模型

| 模型 | 当前 JevBench Intelligence / Capability | 官方文档中的实际约束 |
| --- | --- | --- |
| baselabs mammoth-1 27B | 76.2 / 85.2 | MIT，支持共享输入计算；当前 L4 的显存规模不适合直接按官方 BF16 路径部署 |
| Fastino GLiDE 1.2 27B | 76.4 / 84.9 | 官方要求至少 80 GB GPU，权重约 52.2 GB；每题独立前向；使用 Fastino Community License，不能归为 Apache/MIT 同类许可 |
| Jeff-1.1-Medium 12B | 74.5 / 81.9 | 官方至少 40 GB GPU；权重 CC BY-NC 4.0，非商用；16 槽分组到最多 256 项，启用推理后增加延迟 |

它们适合作为扩大硬件后的效果上限对照，当前不应仅因榜单分高就替换低延迟空调控制模型。上述许可区别直接关系候选能否进入产品；“开放权重”不自动等于无商用限制的开源模型。

## 5. 规范验收与扩展观察的方法

仍沿用 [AC 测试规范](AC_Control_Test_Spec.md)，固定模型版本和官方推理路径。此次新增独占 L4 按顺序测试 Perplexity Flash、KnowLine、Torchcast、Clef，最后测 H2O 同机对照；Liquid 历史结果另列，不称作本轮同机成绩。

1. **规范主成绩：**仅计规范英文原序 S01–S10、M01–M10 共 20 题，报告单/多指令、Key/Value、多余/缺失比例及这 20 次完整请求的耗时。候选反序、10 条英文诊断、24 条英文新题及对应中文翻译均为附项，合计保留每模型 156 次质量观察。中文翻译不算独立新意图，不扩大规范分母。模型选择直接生成指令，不补温度单位、不删除多余动作；没有设备初始状态，因此不报告最终状态指标。Jev/GPT 补跑同一完整请求序列与预热流程，规范分数单独取出。
2. **关键错误：**未提及字段应保持；否定/只改一项；模式与温度单位耦合；上下连续扫风与固定角度；防冻与 DR；两个安静模式；`t_dr_offset=0–31`、`t_dr_mode=0–100` 的完整候选，分别另有 `omit`。
3. **三个时间分别报告：**单字段决策、30 个单字段请求外部串行总耗时、一次提交完整 30 字段的耗时。所有外部请求串行，预热单列；模型内部是否联合、分组或并行也记录，不能把请求数当作前向次数。
4. **部署可复现：**先隔离显存、记录峰值和输入长度，按作者推荐路径实测；快速路径与参考路径的数值差异作为适用限制记录，本轮不另外扩展成所有运行时的准确率交叉测试。禁止静默截断状态或候选；不把额外业务筛选的收益归到原模型。

规范主结果中，KnowLine 与 H2O 均为 18/20，Clef 为 19/20；KnowLine 的完整请求更快。扩展 156 次观察中 H2O 高于 KnowLine，两套分母各自报告。Clef 的内部候选排序、不同引擎与精度、三轮计时的缓存波动等限制均在[部署与扩展记录](AC_CANDIDATE_L4_RESULTS.md)中披露。

## 证据与版本

- [JevBench 摘录及原始文本片段](../validation/model_research/2026-10-30-ac-candidates/leaderboard-extract.json)
- [抓取地址、时间和 SHA-256](../validation/model_research/2026-10-30-ac-candidates/source-manifest.json)，同目录保存官方模型卡、部署说明和相关源码快照。
- [本项目七模型旧业务对照](../validation/open_decision_models/README.zh.md)：89 个案例 × 两种顺序，设备子集为 12 条指令；与完整 AC 测试及 JevBench 分别计分。
- [H2O 官方优化依据](H2O_OFFICIAL_GUIDANCE.md)；[Liquid 准确率优化](LIQUID_AC_OPTIMIZATION.md)。

| 本文重点引用的官方仓库 | 抓取时 revision |
| --- | --- |
| `torchcast-ai/torchcast-decision-4b` | `492bfb19662f3c6e601cc9c4bd2911ac95609ed4` |
| `perplexity-ai/pplx-decider-flash-v1.2` | `9ff7cf9838e59df461c276b7699d56b244d2af58` |
| `PelaAI/KnowLine-4B-Gen5.5` | `779944d2cc8ffa19cef386aee83c83bcb967ade2` |
| `Cloudflare/clef-flash` | `f0b7d3cd65296abfe459e6c228b618f5d8b26d2f` |
| `vllm-sr/d3-mini` | `bd0090dd758d32ba59ef5c749910a8e87fc4391f` |
| `baselabs/mammoth-1` | `61cec44c281c693992e3d6ebeb44dd3402dfa186` |
| `fastino/GLiDE` | `d199b6d7e04523d87986b8b68cd62272ed1cefc0` |
| `jgeuter/Jeff-1.1-Medium` | `540c40924dd67c715d3367309ba6744bac754b00` |
