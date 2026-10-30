# H2O 空调控制运行时优化实测

2026-10-30，在现有 `g6.xlarge` / NVIDIA L4 上实测。H2O、Decider、Liquid 继续同卡常驻；只调整 H2O 服务。模型固定为 `h2oai/h2o-lightning-4b`、FP8、官方补丁 vLLM 0.30.0，GPU 比例 0.34、上下文 4096。没有更换模型、裁剪能力集或根据参考答案修正输出。

**本轮没有找到同时具备明显加速收益、且质量不退步的方案。** causal 完整请求约快 3.46 倍，但诊断题退步；标准编译约减少 10% 耗时，也出现两条质量回退，因此均不采用。已恢复原双向、单序列、eager 配置。**回退复测仍有 N09 与旧基线不同，诊断题为 9/10；配置恢复成功不等于历史选择全部复现，跨重启稳定性问题尚未解决。**

## 测试标准

- 原始规范 20 条 Query，各测原始与反转候选顺序；另测 10 条已有诊断 Query，共 50 条观察。原始与反转属于同一批题，诊断题也不是独立盲测集。
- 每条完整请求包含原来的全部状态、30 个 Key、各 Key 的全部合法值及 `omit`。参考答案仅在本地离线评分，不上传 GPU。
- 外部请求始终串行，前一请求结束后才提交下一请求。`max-num-seqs` 是引擎内部调度上限，并不代表测试客户端并发。
- 性能沿用 S03：“Set the air conditioner temperature to 24 degrees Celsius.”。每配置预热一次，再交替测“一次回答 30 题”和“30 次单 Key 串行请求”，各 3 轮；后者共 90 个真实单步样本。
- 单步耗时是完整状态下单 Key 请求的客户端往返；30 步总耗时取首步开始到末步结束，包含客户端循环开销。一次回答 30 题单独实测，不能用单步乘 30 替代。
- 测量路径为 GPU 主机本机 HTTP。重启、模型加载、编译、健康检查、预热和证据上传不计入正式推理耗时。重复同一 S03 属于预热后的测试，不能外推到所有新输入。
- 先筛性能，值得保留的配置再测完整质量。已因性能淘汰的配置，不能声称其 50 条质量已通过。

本轮默认配置的全部 50 条选择与历史 H2O 基线完全一致。原规范原始顺序 **18/20**、换序 **18/20**，诊断题 **10/10**。

## 配置对照

以下数值均为客户端均值；完整结果以[离线分析](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/optimization_summary.json)为准。

| 配置 | 单 Key | 30 步串行总时间 | 一次回答 30 题 | 原规范 / 换序 / 诊断 | 判断 |
|---|---:|---:|---:|---|---|
| 原配置：双向、seq=1、eager | 199.1 ms | 5.986 s | 5.853 s | 18/20、18/20、10/10 | 基线 |
| 双向、seq=2、eager | 199.0 ms | 5.983 s | 5.764 s | 未做完整质量检查 | 完整请求仅快约 1.5%，单步基本不变 |
| 双向、seq=4、eager | 200.3 ms | 6.022 s | 6.218 s | 未做完整质量检查 | 完整请求变慢 |
| 双向、seq=1、GDN 输入图 4096 | 213.1 ms | 6.405 s | 6.274 s | 未做完整质量检查 | 比原配置慢 |
| 同一 GDN 运行时，显式 causal | 60.8 ms | 1.835 s | 1.692 s | 18/20、18/20、8/10 | 提速但质量退步，不采用 |
| 双向、seq=1、标准编译，GDN 图关闭 | 179.1 ms | 5.384 s | 5.254 s | 18/20、18/20、8/10 | 约快 10%，但质量退步，不采用 |
| 恢复原配置后重新测量 | 200.1 ms | 6.014 s | 5.871 s | 18/20、18/20、9/10 | 最终运行配置；N09 未复现历史选择 |

标准编译的性能与质量分两次运行，复用同一个容器进程和相同配置；质量依据 `seq1-compiled-quality` 的完整 50 条观察，不以 S03 的正确输出代替全套验证。

`seq=2` 的小幅差异来自按配置依次测量的三轮样本，未做跨配置交错重复，不能据此宣称稳定收益。`seq=4` 也没有改善单步延迟。厂商启动脚本最后追加 `--max-num-batched-tokens "$MAX_LEN"`，本部署预算仍为 4096；仅增大序列上限不会自动消除重复上下文计算。本轮未同时增大 token 预算或其他模型的显存限额。

GDN 输入图与标准 `torch.compile` / vLLM CUDA graph 是两条配置路径。本轮先保持 `--enforce-eager`，单独设置 GDN 最大 token 数 4096、预捕获开启、最大序列数 1；然后单独关闭 GDN 图、移除 `--enforce-eager` 测标准编译，编译线程限制为 1。不能把两种实验混成一个“开启图加速”的结论。

标准编译日志确认 `torch.compile` 实际执行了 **41.89 秒**，CUDA graph 捕获成功，最终图池报告 **0.03 GiB**；从服务重启到 shim 就绪总共 **282.72 秒**。这些开销不在上表的预热后耗时中。启动时使用新的独立缓存目录，不能据此断言已有编译缓存下的重启仍需相同时间。编译范围覆盖 1–4096 token，图捕获上限保持 128；本轮未单独剥离编译和图重放各自的贡献。

编译方案的 S03 完整请求仍报告处理 **40,137** token，与默认双向模式相同；输入、候选与模式没有减少。单步 P95 从 **240.2 ms** 降到 **215.6 ms**；完整请求三轮分别 **5.218 / 5.262 / 5.282 秒**，原配置为 **5.825 / 5.854 / 5.878 秒**。性能收益比 `seq=2` 更明显，但后续质量检查未通过。

## causal 为什么快、为什么没有采用

在同一个已加载的 GDN 运行时，只通过请求字段 `attention_mode: "causal"` 切换模式，服务默认始终保持双向。完整 S03 的服务返回 `processed_input_tokens` 从 **40,137** 降至 **6,468**，虽然业务 `input_tokens` 都是 **6,468**。这说明两种模式处理共享状态的方式不同；该字段本身不是独立测得的 KV 缓存命中率。

causal 相对原配置，完整请求约快 **3.46 倍**、单步约快 **3.28 倍**，但出现两条额外误操作：

| 题目 | 应输出 | causal 实际输出 |
|---|---|---|
| N09：Enable vertical oscillation and point horizontal airflow straight ahead. | `t_up_down=1`、`t_swing_direction=0` | 两项正确，同时多输出 `t_swing_angle=0` |
| N10：Enable fresh air while keeping healthy wind unchanged. | `t_fresh_air=1` | 新风正确，同时多输出 `t_health_fan=1` |

这两题在默认双向模式正确。尤其 N10 明确要求保持健康风不变，额外打开健康风违背指令，因此不能只看 20 条原规范分数相同就切换默认模式。本轮保留原始模型选择，没有用规则删除错误字段。

## 标准编译的质量回退

编译方案原规范及换序的 40 条观察保持原选择；诊断题 N03、N09 改变并由正确变错：

| 题目 | 应输出 | 编译后实际输出 |
|---|---|---|
| N03：Enable 8-degree frost protection; leave the operating mode unchanged. | `t_8heat=1` | 防冻正确，同时多输出 `t_dr_offset=8` |
| N09：Enable vertical oscillation and point horizontal airflow straight ahead. | `t_up_down=1`、`t_swing_direction=0` | 两项正确，同时多输出 `t_swing_angle=0` |

N03 的 `t_dr_offset` 题中，原配置返回 `omit` 概率约 0.716、`8` 约 0.255；编译配置返回 `omit` 约 0.480、`8` 约 0.490，最终选成 `8`。这是模型返回的分布与选择发生变化，不是评分程序误读。

本轮没有进一步逐个隔离编译算子、FP8 数值路径或 CUDA graph 重放，因此不能宣称已定位到底层某个 kernel。仅凭“输入与模型相同”也不能假定编译后输出必然等价。为避免将重启影响误归于编译，回退后另做原配置复核。

## 回退复核与重启前后不一致

移除试验 drop-in、恢复原 systemd 配置后，另测同样的 3 轮性能和完整 50 条质量。**49/50 条选择与最初基线一致；N03、N10 恢复原选择，N09 仍多输出 `t_swing_angle=0`。** 原规范及换序成绩仍为 18/20、18/20，诊断题为 9/10。这条失败保留在复测分母中。

随后追加 12 次固定输入检查：N03、N09、N10 各三次完整 30 题请求，另测三次 N09 的 `t_swing_angle` 单 Key 请求，全部串行、完整状态及原候选保持不变。N03、N10 始终正确；N09 六次都选择错误的 `0`，且该题概率字典完全一致。N09 回退后的 `omit` / `0` 概率约 **0.344 / 0.616**，最初基线为 **0.584 / 0.372**。

因此，本次观察支持“当前进程内结果稳定、重启前后结果不同”，不能把 N09 的全部变化归于编译，也不能把它解释成客户端并发、偶发采样或单 Key 封装造成。本轮没有定位初始化或底层数值路径的根因；补充观察单独统计，原复测诊断分数仍为 9/10。

最终部署仍使用原参数、原 Docker 镜像和原服务源码；systemd 配置逐字恢复、故障重启策略为 `always`，试验 drop-in 与自动回退定时器均已移除。Decider、Liquid、对比网关的启动时间及重启次数保持不变。安装脚本没有改成编译或 causal 配置。

共保存 **863 次正式调用**（851 次主试验、12 次补充重复验证）及 **8 次预热**，全部有效且无请求重叠。[最终审计](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/audit.json)的 `passed` 表示证据、串行执行与配置恢复检查通过；其中 `historical_choices_reproduced_after_rollback: false` 明确表示质量未完全复现。另见[最终运行时](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/final_runtime.json)、[配置选择记录](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/selection.json)和[重复验证响应](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/repeatability/receipts.jsonl)。

## 后续优化方向

补充[官方文档与当前部署对照](H2O_OFFICIAL_GUIDANCE.md)：官方明确双向模式不读写前缀缓存，共享长状态的多题请求可考虑 causal；单向多题默认保持 `SHIM_CACHE_WRITE=all`，`first` 的单题收益不能直接套用。文档还区分 BF16／FP8、24GB 卡的 GDN 图档位、双向批次预算与配置独立编译缓存。官方已部署版本源码哈希核对一致；本次仅查阅，没有改动服务或新增推理实测。

应先定位重启前后的输出差异，建立可复现的运行基线，再继续比较加速配置。现有显存、完整输入和同卡常驻约束下，只调大并发没有明显收益。其他方向包括在独立实验中隔离编译路径的选择偏移，或联合评估 causal 与通用规则澄清，并增加独立新题验证。已有五模型报告中“仅改规则”对 H2O 有帮助，但尚未证明能消除本轮 causal 的回退。

更高精度、更多显存或独占 GPU 也属于新的部署条件，不能直接套用本轮结果。本轮没有调整其他模型的资源、扩大实例或自动修改提示词。

## 证据与复现

全部原始输入、候选、响应文本、模型选择、时间戳、运行时参数及备份位于 [2026-10-30-h2o-optimization-v1](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/)。

- [冻结测试计划](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/plan.json)、[完整输入](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/cases.json)、[历史基线复现](../validation/ac_control/runs/2026-10-30-h2o-optimization-v1/baseline_reproduction.json)。
- [串行测量脚本](../validation/ac_control/run_h2o_optimization.py)：真实请求、禁止覆盖观察、无自动重试。
- [部署试验控制器](../deployment/open_models/tune_h2o_runtime.py)：只修改 H2O systemd drop-in，启动失败恢复原配置；试验有 25 分钟自动回退保护，最终接受配置后解除保护并恢复正常故障重启策略。
- [离线分析](../validation/ac_control/analyze_h2o_optimization.py)、[最终审计](../validation/ac_control/audit_h2o_optimization.py)：检查输入与源码哈希、串行时间戳、原始选择和独立质量证据、其他服务及最终配置。
- [重复验证脚本](../validation/ac_control/recheck_h2o_repeatability.py)：补充检查重启后的 N09，不覆盖已有观察或分数。

只读复核：

```bash
python validation/ac_control/analyze_h2o_optimization.py \
  --run validation/ac_control/runs/2026-10-30-h2o-optimization-v1
python validation/ac_control/audit_h2o_optimization.py \
  --run validation/ac_control/runs/2026-10-30-h2o-optimization-v1
.venv/bin/python -m pytest -q validation/ac_control/test_h2o_optimization.py
```

本轮是现有 AC 基线的运行时调优；历史[五模型报告](AC_CONTROL_COMPARISON.md)中的模型、提示词和性能数据仍属于各自原批次。没有重新测量 Jev、GPT、Decider、Liquid，也没有向真实空调下发控制。
