# 开放权重决策模型：同一台 L4 GPU 的业务对比

2026-10-29 · [English](README.md)

本轮比较 **Strands Decider v19、Liquid d1-2B、Perplexity Decider Flash v1.2、KnowLine-4B-Gen5.5、H2O-Lightning-4B v1.4.1**，并使用 Jev 1.14.0 和 GPT 6.1 Sol low 作为 API 对照。模型均未在本项目中微调。

初轮旧 GPU 控制器自动恢复了后台模型，影响可用显存；该批次保存在 `initial_shared_gpu/`，未混入下表。最终 GPU 数据来自暂停控制器后的复测，每个模型启动前检查空闲显存，见 [环境修正记录](isolation_correction.json)。API 对照保留原始调用。

五个本地模型依次运行在现有 **g6.xlarge / NVIDIA L4 24 GB / 4 vCPU / 16 GiB RAM** 上。Strands 基线为原生 CUDA；这是指定的非 vLLM 实例，在线 vLLM 实例未参与测试。具体版本、权重校验和与运行方式见 [models.json](models.json)、[hardware.json](hardware.json) 和 `environment-*.json`。

## 1. 判断效果

89 个独立案例，各测试原始、反转两种候选顺序，即每模型 178 次质量请求，共 1246 次。多问题请求必须全部符合参考，才计为该案例通过；格式失败也计入分母。以下数字是**与本批次参考策略一致的次数**，不是通用准确率或 JevBench 榜单分数。

| 模型 | 支付步骤 | 模型路由 | 设备指令 | 温度多选 | 调用/格式失败 |
| --- | --- | --- | --- | --- | --- |
| Strands Decider v19 | 66/80 | 26/64 | 13/24 | 10/10 | 0 |
| Liquid d1-2B | 77/80 | 35/64 | 17/24 | 10/10 | 0 |
| Perplexity Decider Flash v1.2 | 80/80 | 47/64 | 16/24 | 9/10 | 0 |
| KnowLine-4B-Gen5.5 | 80/80 | 42/64 | 19/24 | 10/10 | 0 |
| H2O-Lightning-4B v1.4.1 | 80/80 | 54/64 | 17/24 | 10/10 | 0 |
| Jev 1.14.0 | 80/80 | 59/64 | 20/24 | 10/10 | 0 |
| GPT 6.1 Sol low | 78/80 | 59/64 | 14/24 | 10/10 | 12 |

输入与参考在调用前冻结：[请求](requests.json)、[参考及依据](references.json)、[计划](plan.json)。参考答案只用于离线评分，模型收到业务状态、问题及完整候选项。

- 支付：4 个业务 × 待处理/就绪 × 5 步骤，共 40 个快照；所有模型使用相同的 `optimized` 输入。后续快照由参考流程生成，本次不是模型自主执行的连续交易。
- 路由：复用既有验证的 32 个任务。模型目录能力、价格来自冻结快照，健康状态等是测试设定；没有调用选中的下游模型，也不是前端最新区域目录的在线测评。
- 设备：12 条中英文指令，分别选择电源、16–30°C 整数温度及模式；包括否定、相对调整、越界和小数。
- 多选：5 个集合任务，共同协议为 15 个独立二选一问题。Liquid 的原生多选另测，不混入这张表。

### 路由应分成两类看

| 模型 | 任务类型分流 | 能力限制 | 成本/预算 | 可用性/回退/偏好 |
| --- | --- | --- | --- | --- |
| Strands Decider v19 | 16/16 | 2/16 | 5/16 | 3/16 |
| Liquid d1-2B | 16/16 | 12/16 | 2/16 | 5/16 |
| Perplexity Decider Flash v1.2 | 16/16 | 10/16 | 8/16 | 13/16 |
| KnowLine-4B-Gen5.5 | 16/16 | 6/16 | 7/16 | 13/16 |
| H2O-Lightning-4B v1.4.1 | 15/16 | 16/16 | 11/16 | 12/16 |
| Jev 1.14.0 | 16/16 | 13/16 | 14/16 | 16/16 |
| GPT 6.1 Sol low | 11/16 | 16/16 | 16/16 | 16/16 |

“任务类型分流”是选择代码、推理、视觉等处理流程；后三列要求同时比较多个候选的具体条件。Strands、Liquid、Perplexity、KnowLine 和 Jev 在本批任务分流上均为 16/16。GPT 的 5 次差异全部选择了 `clarify`：描述称源码、堆栈或证明已提供，GPT 仍要求补充材料。这里评估的是任务应进入哪个流程，没有实际执行下游代码分析或证明；这类差异需要结合任务边界理解。

## 2. 速度

质量请求中，成功调用的中位耗时如下，单位 ms。一轮请求可能包含 1、3 或 15 个判断。

| 模型 | 支付 | 路由 | 设备三判断 | 温度十五判断 |
| --- | --- | --- | --- | --- |
| Strands Decider v19 | 65.4 | 188.8 | 232.6 | 277.1 |
| Liquid d1-2B | 38.6 | 114.3 | 60.6 | 71.7 |
| Perplexity Decider Flash v1.2 | 144.8 | 500.1 | 247.6 | 290.2 |
| KnowLine-4B-Gen5.5 | 314.6 | 1153.1 | 851.7 | 3188.8 |
| H2O-Lightning-4B v1.4.1 | 93.4 | 275.0 | 201.0 | 369.3 |
| Jev 1.14.0 | 74.9 | 87.3 | 80.0 | 74.3 |
| GPT 6.1 Sol low | 920.6 | 1022.2 | 1023.5 | 2268.8 |

本地 GPU 列从实例内调用 loopback 接口；Jev/GPT 列包含从 us-east-1 客户端到云 API 的网络往返。因此这些是各测试服务的请求耗时，不能直接当作跨厂商纯 GPU 推理耗时。

运行方式影响很大：Strands 使用原版 SDK；Liquid 使用官方 Transformers 实现；Perplexity 使用官方 `fast=False` 参考路径；KnowLine 使用官方 HF BF16 路径并启用 read-twice，未使用作者推荐的 SGLang FP8。后两者没有安装快速卷积/线性注意力内核。H2O 使用其指定 vLLM 0.30.0 Python 覆盖文件、双向注意力和 eager 模式，最大上下文 8192。以上结果不代表所有模型的最优部署性能。

<details>
<summary>预热后的 1 / 4 / 8 并发结果</summary>

每档使用相同的 8 个案例各重复 4 次，共 32 个请求、160 个判断；不混入加载模型的时间。P50/P95 只统计有效响应，吞吐是有效请求数除以整批耗时。“请求/秒”不是 token/秒。Strands、Liquid、Perplexity 和 KnowLine 包装服务采用串行 CUDA 执行；并发会产生排队，不能把这些数值视作它们的批处理上限。

| 模型 | 并发 | P50 ms | P95 ms | 有效请求/秒 | 有效返回 |
| --- | --- | --- | --- | --- | --- |
| Strands Decider v19 | 1 | 208.6 | 279.8 | 5.69 | 32/32 |
| Strands Decider v19 | 4 | 594.1 | 1017.5 | 5.73 | 32/32 |
| Strands Decider v19 | 8 | 1394.3 | 1423.1 | 5.71 | 32/32 |
| Liquid d1-2B | 1 | 59.6 | 112.2 | 16.43 | 32/32 |
| Liquid d1-2B | 4 | 232.3 | 313.6 | 16.50 | 32/32 |
| Liquid d1-2B | 8 | 482.7 | 498.3 | 16.41 | 32/32 |
| Perplexity Decider Flash v1.2 | 1 | 244.6 | 512.8 | 4.14 | 32/32 |
| Perplexity Decider Flash v1.2 | 4 | 907.2 | 1333.0 | 4.14 | 32/32 |
| Perplexity Decider Flash v1.2 | 8 | 1938.8 | 1945.8 | 4.13 | 32/32 |
| KnowLine-4B-Gen5.5 | 1 | 849.2 | 3178.3 | 0.79 | 32/32 |
| KnowLine-4B-Gen5.5 | 4 | 4912.3 | 8355.5 | 0.79 | 32/32 |
| KnowLine-4B-Gen5.5 | 8 | 10066.0 | 10159.0 | 0.79 | 32/32 |
| H2O-Lightning-4B v1.4.1 | 1 | 205.5 | 362.2 | 4.85 | 32/32 |
| H2O-Lightning-4B v1.4.1 | 4 | 712.1 | 1256.9 | 5.08 | 32/32 |
| H2O-Lightning-4B v1.4.1 | 8 | 1182.8 | 2022.9 | 5.22 | 32/32 |
| Jev 1.14.0 | 1 | 69.3 | 126.6 | 12.60 | 32/32 |
| Jev 1.14.0 | 4 | 80.0 | 110.5 | 47.00 | 32/32 |
| Jev 1.14.0 | 8 | 77.0 | 107.7 | 91.42 | 32/32 |
| GPT 6.1 Sol low | 1 | 987.2 | 2582.4 | 0.70 | 31/32 |
| GPT 6.1 Sol low | 4 | 1020.5 | 3091.6 | 2.21 | 29/32 |
| GPT 6.1 Sol low | 8 | 1053.2 | 2235.5 | 4.79 | 31/32 |

原始指标：[performance_summary.json](results/performance_summary.json)。

</details>

## 3. 请求与结果举例

下表均为原始候选顺序的真实返回：

1. 入账执行：129 USDC 足额、12/12 确认，参考动作为 `credit_order`。
2. 温度调整：当前 26°C，用户说“把设定温度降低2度，其他不变”，参考温度为 `24`。
3. 调试任务分流：用户描述“给定堆栈与源码，分析连接池死锁并给出最小修复”，参考路由为 `code_analysis`。

| 模型 | 入账执行 | 目标温度 | 调试流程 |
| --- | --- | --- | --- |
| Strands Decider v19 | hold | 18 | code_analysis |
| Liquid d1-2B | credit_order | 24 | code_analysis |
| Perplexity Decider Flash v1.2 | credit_order | 24 | code_analysis |
| KnowLine-4B-Gen5.5 | credit_order | 24 | code_analysis |
| H2O-Lightning-4B v1.4.1 | credit_order | 24 | code_analysis |
| Jev 1.14.0 | credit_order | 24 | code_analysis |
| GPT 6.1 Sol low | credit_order | JSON error | clarify |

Strands 在这个入账样本中选择 `hold`，实际效果是继续等待。GPT 的 `JSON error` 表示返回无法严格解析，没有替它补括号或重试。有效 JSON 的选择错误和接口格式问题分别保存在 [mismatches.json](results/mismatches.json)。

### 动作不同，对业务的影响也不同

我们把冻结的支付单步快照及真实模型选择交给现有沙盒执行函数，并单独核对设备最终设置：

| 模型 | 支付保护纠正 | 模拟记账/8次机会 | 路由违反硬条件/48 | 错误拒绝路由/48 | 设备最终状态/24 |
| --- | --- | --- | --- | --- | --- |
| Strands Decider v19 | 2 | 3/8 | 27 | 7 | 17/24 |
| Liquid d1-2B | 3 | 8/8 | 23 | 3 | 19/24 |
| Perplexity Decider Flash v1.2 | 0 | 8/8 | 3 | 9 | 18/24 |
| KnowLine-4B-Gen5.5 | 0 | 8/8 | 4 | 15 | 23/24 |
| H2O-Lightning-4B v1.4.1 | 0 | 8/8 | 7 | 0 | 17/24 |
| Jev 1.14.0 | 0 | 8/8 | 2 | 1 | 21/24 |
| GPT 6.1 Sol low | 0 | 6/8 | 0 | 0 | 14/24 |

这里的记账只是**独立快照的模拟执行**；没有真实转账，也不能据此声称完整交易已连续跑通。路由另有“候选合法、但未满足优先规则”的情况，详见 [business_audit.json](results/business_audit.json)。设备初始状态为关闭、26°C、制热；最终状态允许“保持不变”和“再次设置为当前值”等价，严格指令表则保留两者的差异。

## 4. Liquid 原生多选

使用 `type: "choice", multiple: true`，候选为 16–30°C。5/5 例集合完全一致，单次耗时 30.9–32.2 ms（本机参考实现，原始候选顺序）。

```json
{
  "state": "Select every integer temperature from 22 to 25 Celsius, inclusive.",
  "questions": {
    "temperatures": {
      "type": "choice",
      "instructions": "Select all and only the temperatures requested as presets.",
      "criteria": {
        "16": "16 degrees Celsius",
        "17": "17 degrees Celsius",
        "18": "18 degrees Celsius",
        "19": "19 degrees Celsius",
        "20": "20 degrees Celsius",
        "21": "21 degrees Celsius",
        "22": "22 degrees Celsius",
        "23": "23 degrees Celsius",
        "24": "24 degrees Celsius",
        "25": "25 degrees Celsius",
        "26": "26 degrees Celsius",
        "27": "27 degrees Celsius",
        "28": "28 degrees Celsius",
        "29": "29 degrees Celsius",
        "30": "30 degrees Celsius"
      },
      "multiple": true
    }
  }
}
```

实际请求包含所有 15 个候选；返回 `["22","23","24","25"]`。其他样例覆盖 22 与 26、多项显式选择、排除 22/26 和空集合。完整输入与返回见 [原生多选请求](liquid_native_multiselect.json) 和 [实测记录](results/liquid-native-multiselect.jsonl)。

## 5. 换序与适用范围

| 模型 | 换序后动作有变化 / 两次均有效的案例 |
| --- | --- |
| Strands Decider v19 | 17/89 |
| Liquid d1-2B | 10/89 |
| Perplexity Decider Flash v1.2 | 5/89 |
| KnowLine-4B-Gen5.5 | 7/89 |
| H2O-Lightning-4B v1.4.1 | 3/89 |
| Jev 1.14.0 | 7/89 |
| GPT 6.1 Sol low | 1/81 |

两种顺序是同一案例的重复观察。对 API 模型，变化也可能包含服务数值波动或生成随机性；本轮没有把所有变化都归因于位置偏差。GPT 有格式失败，因此可成对比较的案例数较少。

### 哪些模型值得继续比较

- **本地部署、优先判断效果：H2O-Lightning 4B。** 支付 80/80、路由 54/64，整体案例 161/178，均为本轮本地模型最高。支付中位 93 ms，具备继续验证的价值；复杂路由仍有 7/48 次违反硬条件，尚不能直接替代约束检查。
- **低延迟、设备动作及多选：Liquid d1-2B。** 支付 77/80、中位 39 ms；三项设备判断中位 61 ms；原生集合多选 5/5。它适合优先验证快速局部决策，但复杂路由仅 35/64，23/48 次违反硬条件，不能由速度推断选模效果。
- **支付流程另一个候选：Perplexity Flash。** 支付 80/80、8/8 次模拟记账，支付中位 145 ms。路由 47/64；当前参考推理路径的速度还有单独优化空间。
- **设备最终设置：KnowLine 值得保留。** 严格动作 19/24、最终状态 23/24；支付 80/80。代价是本次 HF 路径较慢，设备中位 852 ms；应验证推荐部署后再决定是否适合高频调用。
- **现有 Strands：继续用于任务分流与经过验证的局部判断。** 任务类型分流 16/16，支付中位 65 ms；本轮支付 66/80、完整路由 26/64，说明跨条件判断和执行时机仍需改进。下一步应明确条件适用范围、加入反例与完成条件，再用独立留出集验证微调；本轮没有测这些优化的收益。
- **托管 API：Jev 本轮整体参考一致性最好。** 169/178，支付/路由中位 75/87 ms，8 并发有效吞吐 91.42 请求/秒。GPT 在 48 个具体约束路由观察中为 48/48，但支付/路由耗时约 0.92/1.02 秒，另有 12 次质量响应格式失败。

GPT 使用提示词约定 JSON，没有启用受约束的结构化输出；12 次失败中支付 2 次、设备 10 次，均保留原始返回。应先改进接口输出契约再复测，不能把格式失败直接解释成推理能力不足。有效响应中，GPT 与参考一致 161/166；主表仍按全部 178 次计算。

这些结论只适用于本批固定输入。预算计算、条件范围、材料完整性和“无需改动”的语义都可能影响选择；榜单总分不能代替业务验证，也不能据此宣称某个模型普遍更智能。

## 6. 数据与复现

测试结束后，原有文字模型、图片服务、GPU 控制器和定时规则均已恢复，实例保持运行。临时模型环境及 S3 安装文件已清理，原始测量记录保留；见 [恢复记录](restoration.json)。

- [质量汇总](results/summary.json)、[错误及差异](results/mismatches.json)、[逐次原始返回](results/)。
- [模型固定版本与校验和](models.json)、[保持候选顺序的请求哈希](ordered_request_hashes.json)。
- `prepare.py` 冻结计划；`run.py` 发起调用并严格解析；`analyze.py`、`business_audit.py`、`performance.py` 离线评分。
- `gpu_server.py` 包装官方实现；`trial.py` 完成单个模型的质量与并发测试并关闭进程。GPU 离线安装、临时控制及下载脚本位于同目录，凭据与私有签名清单位于被忽略的 `.deployment/`。

```bash
python -m unittest discover -s validation/open_decision_models -p 'test_*.py'
python validation/open_decision_models/analyze.py
.venv/bin/python validation/open_decision_models/business_audit.py
python validation/open_decision_models/performance.py
python validation/open_decision_models/report.py
```

选型参考：[JevBench](https://benchmarkheaven.com/jev-models)、[API/方法](https://benchmarkheaven.com/jev-models/api)、[Liquid d1-2B](https://huggingface.co/LiquidAI/d1-2B)、[Perplexity Flash](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2)、[KnowLine](https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5)、[H2O-Lightning](https://huggingface.co/h2oai/h2o-lightning-4b)。本轮没有运行完整 JevBench，也不复用其分数计算业务通过率。
