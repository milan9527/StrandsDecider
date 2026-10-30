"""Generate bilingual tables directly from completed evidence summaries."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
ORDER = ["decider", "liquid", "pplx", "knowline", "h2o", "jev", "gpt"]
NAMES = {
    "decider": "Strands Decider v19",
    "liquid": "Liquid d1-2B",
    "pplx": "Perplexity Decider Flash v1.2",
    "knowline": "KnowLine-4B-Gen5.5",
    "h2o": "H2O-Lightning-4B v1.4.1",
    "jev": "Jev 1.14.0",
    "gpt": "GPT 6.1 Sol low",
}
GROUPS = ["payment", "routing", "device_control", "temperature_multiselect"]
CATEGORIES = ["semantic_task_routing", "capability_constraints", "cost_and_budget",
              "availability_fallback_and_preferences"]


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join(["---"] * len(headers)) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def main():
    quality = json.loads((ROOT / "results/summary.json").read_text())
    performance = json.loads((ROOT / "results/performance_summary.json").read_text())
    audit = json.loads((ROOT / "results/business_audit.json").read_text())["summary"]
    assert all(quality[p]["complete"] and set(performance[p]) == {"1", "4", "8"} for p in ORDER)
    quality_rows = [[NAMES[p], *[f'{quality[p]["groups"][g]["exact_cases"]}/{quality[p]["groups"][g]["requests"]}'
                                 for g in GROUPS], quality[p]["overall"]["call_or_format_failures"]] for p in ORDER]
    routing_rows = [[NAMES[p], *[f'{quality[p]["routing_categories"][c]["exact_cases"]}/16' for c in CATEGORIES]]
                    for p in ORDER]
    latency_rows = [[NAMES[p], *[f'{quality[p]["groups"][g]["client_p50_ms"]:.1f}' for g in GROUPS]] for p in ORDER]
    audit_rows = [[NAMES[p], audit[p].get("payment_safety_adjustments", 0),
                   f'{audit[p].get("payment_simulated_ledger_entries", 0)}/{audit[p]["payment_reference_ledger_opportunities"]}',
                   audit[p].get("routing_hard_constraint_violation", 0),
                   audit[p].get("routing_false_no_route", 0),
                   f'{audit[p].get("device_final_state_matches", 0)}/24'] for p in ORDER]
    perf_rows = [[NAMES[p], c, f'{performance[p][str(c)]["client_p50_ms"]:.1f}',
                 f'{performance[p][str(c)]["client_p95_ms"]:.1f}',
                 f'{performance[p][str(c)]["successful_requests_per_second"]:.2f}',
                 f'{performance[p][str(c)]["success"]}/32']
                for p in ORDER for c in (1, 4, 8)]
    flip_rows = [[NAMES[p], f'{quality[p]["overall"]["candidate_order_flip_cases"]}/{quality[p]["overall"]["valid_order_pairs"]}']
                for p in ORDER]
    examples = {}
    for p in ORDER:
        examples[p] = {(r["case_id"], r["variant"]): r for r in map(
            json.loads, (ROOT / f"results/{p}-quality.jsonl").read_text().splitlines())}
    def result(p, cid, key):
        row = examples[p][cid, "original"]
        return row["choices"][key] if row["status"] == "ok" else "JSON error"
    example_rows = [[NAMES[p], result(p, "payment-pending-ready-execute", "action"),
                     result(p, "device-06", "temperature"), result(p, "routing-intent-debug", "action")]
                    for p in ORDER]
    native = [json.loads(line) for line in (ROOT / "results/liquid-native-multiselect.jsonl").read_text().splitlines()]
    expected_native = {r["case_id"]: set(r["expected"]) for r in json.loads(
        (ROOT / "liquid_native_multiselect.json").read_text())}
    native_correct = sum(r["status"] == "ok" and
                         set(r["response"]["answers"]["temperatures"]["choices"]) == expected_native[r["case_id"]]
                         for r in native)
    native_times = [r["client_ms"] for r in native]
    native_range = f"{min(native_times):.1f}–{max(native_times):.1f}"
    native_request = next(r["request"] for r in json.loads(
        (ROOT / "liquid_native_multiselect.json").read_text()) if r["case_id"] == "temperature-set-03")
    total = sum(quality[p]["overall"]["requests"] for p in ORDER)
    zh = f"""# 开放权重决策模型：同一台 L4 GPU 的业务对比

2026-10-29 · [English](README.md)

本轮比较 **Strands Decider v19、Liquid d1-2B、Perplexity Decider Flash v1.2、KnowLine-4B-Gen5.5、H2O-Lightning-4B v1.4.1**，并使用 Jev 1.14.0 和 GPT 6.1 Sol low 作为 API 对照。模型均未在本项目中微调。

初轮旧 GPU 控制器自动恢复了后台模型，影响可用显存；该批次保存在 `initial_shared_gpu/`，未混入下表。最终 GPU 数据来自暂停控制器后的复测，每个模型启动前检查空闲显存，见 [环境修正记录](isolation_correction.json)。API 对照保留原始调用。

五个本地模型依次运行在现有 **g6.xlarge / NVIDIA L4 24 GB / 4 vCPU / 16 GiB RAM** 上。Strands 基线为原生 CUDA；这是指定的非 vLLM 实例，在线 vLLM 实例未参与测试。具体版本、权重校验和与运行方式见 [models.json](models.json)、[hardware.json](hardware.json) 和 `environment-*.json`。

## 1. 判断效果

89 个独立案例，各测试原始、反转两种候选顺序，即每模型 178 次质量请求，共 {total} 次。多问题请求必须全部符合参考，才计为该案例通过；格式失败也计入分母。以下数字是**与本批次参考策略一致的次数**，不是通用准确率或 JevBench 榜单分数。

{table(["模型", "支付步骤", "模型路由", "设备指令", "温度多选", "调用/格式失败"], quality_rows)}

输入与参考在调用前冻结：[请求](requests.json)、[参考及依据](references.json)、[计划](plan.json)。参考答案只用于离线评分，模型收到业务状态、问题及完整候选项。

- 支付：4 个业务 × 待处理/就绪 × 5 步骤，共 40 个快照；所有模型使用相同的 `optimized` 输入。后续快照由参考流程生成，本次不是模型自主执行的连续交易。
- 路由：复用既有验证的 32 个任务。模型目录能力、价格来自冻结快照，健康状态等是测试设定；没有调用选中的下游模型，也不是前端最新区域目录的在线测评。
- 设备：12 条中英文指令，分别选择电源、16–30°C 整数温度及模式；包括否定、相对调整、越界和小数。
- 多选：5 个集合任务，共同协议为 15 个独立二选一问题。Liquid 的原生多选另测，不混入这张表。

### 路由应分成两类看

{table(["模型", "任务类型分流", "能力限制", "成本/预算", "可用性/回退/偏好"], routing_rows)}

“任务类型分流”是选择代码、推理、视觉等处理流程；后三列要求同时比较多个候选的具体条件。Strands、Liquid、Perplexity、KnowLine 和 Jev 在本批任务分流上均为 16/16。GPT 的 5 次差异全部选择了 `clarify`：描述称源码、堆栈或证明已提供，GPT 仍要求补充材料。这里评估的是任务应进入哪个流程，没有实际执行下游代码分析或证明；这类差异需要结合任务边界理解。

## 2. 速度

质量请求中，成功调用的中位耗时如下，单位 ms。一轮请求可能包含 1、3 或 15 个判断。

{table(["模型", "支付", "路由", "设备三判断", "温度十五判断"], latency_rows)}

本地 GPU 列从实例内调用 loopback 接口；Jev/GPT 列包含从 us-east-1 客户端到云 API 的网络往返。因此这些是各测试服务的请求耗时，不能直接当作跨厂商纯 GPU 推理耗时。

运行方式影响很大：Strands 使用原版 SDK；Liquid 使用官方 Transformers 实现；Perplexity 使用官方 `fast=False` 参考路径；KnowLine 使用官方 HF BF16 路径并启用 read-twice，未使用作者推荐的 SGLang FP8。后两者没有安装快速卷积/线性注意力内核。H2O 使用其指定 vLLM 0.30.0 Python 覆盖文件、双向注意力和 eager 模式，最大上下文 8192。以上结果不代表所有模型的最优部署性能。

<details>
<summary>预热后的 1 / 4 / 8 并发结果</summary>

每档使用相同的 8 个案例各重复 4 次，共 32 个请求、160 个判断；不混入加载模型的时间。P50/P95 只统计有效响应，吞吐是有效请求数除以整批耗时。“请求/秒”不是 token/秒。Strands、Liquid、Perplexity 和 KnowLine 包装服务采用串行 CUDA 执行；并发会产生排队，不能把这些数值视作它们的批处理上限。

{table(["模型", "并发", "P50 ms", "P95 ms", "有效请求/秒", "有效返回"], perf_rows)}

原始指标：[performance_summary.json](results/performance_summary.json)。

</details>

## 3. 请求与结果举例

下表均为原始候选顺序的真实返回：

1. 入账执行：129 USDC 足额、12/12 确认，参考动作为 `credit_order`。
2. 温度调整：当前 26°C，用户说“把设定温度降低2度，其他不变”，参考温度为 `24`。
3. 调试任务分流：用户描述“给定堆栈与源码，分析连接池死锁并给出最小修复”，参考路由为 `code_analysis`。

{table(["模型", "入账执行", "目标温度", "调试流程"], example_rows)}

Strands 在这个入账样本中选择 `hold`，实际效果是继续等待。GPT 的 `JSON error` 表示返回无法严格解析，没有替它补括号或重试。有效 JSON 的选择错误和接口格式问题分别保存在 [mismatches.json](results/mismatches.json)。

### 动作不同，对业务的影响也不同

我们把冻结的支付单步快照及真实模型选择交给现有沙盒执行函数，并单独核对设备最终设置：

{table(["模型", "支付保护纠正", "模拟记账/8次机会", "路由违反硬条件/48", "错误拒绝路由/48", "设备最终状态/24"], audit_rows)}

这里的记账只是**独立快照的模拟执行**；没有真实转账，也不能据此声称完整交易已连续跑通。路由另有“候选合法、但未满足优先规则”的情况，详见 [business_audit.json](results/business_audit.json)。设备初始状态为关闭、26°C、制热；最终状态允许“保持不变”和“再次设置为当前值”等价，严格指令表则保留两者的差异。

## 4. Liquid 原生多选

使用 `type: "choice", multiple: true`，候选为 16–30°C。{native_correct}/{len(native)} 例集合完全一致，单次耗时 {native_range} ms（本机参考实现，原始候选顺序）。

```json
{json.dumps(native_request, ensure_ascii=False, indent=2)}
```

实际请求包含所有 15 个候选；返回 `["22","23","24","25"]`。其他样例覆盖 22 与 26、多项显式选择、排除 22/26 和空集合。完整输入与返回见 [原生多选请求](liquid_native_multiselect.json) 和 [实测记录](results/liquid-native-multiselect.jsonl)。

## 5. 换序与适用范围

{table(["模型", "换序后动作有变化 / 两次均有效的案例"], flip_rows)}

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
"""
    en = f"""# Open-weight decision models on one NVIDIA L4

2026-10-29 · [中文](README.zh.md)

We tested Strands Decider v19, Liquid d1-2B, Perplexity Decider Flash v1.2, KnowLine-4B-Gen5.5 and H2O-Lightning-4B v1.4.1 sequentially on the existing **g6.xlarge: L4 24 GB, 4 vCPUs, 16 GiB RAM**. Jev 1.14.0 and GPT 6.1 Sol low are API controls. Strands uses native CUDA; the online vLLM instance did not participate. No model weights were fine-tuned for this test.

The legacy GPU controller resumed a background model during the initial round. Those observations are retained in `initial_shared_gpu/` and excluded below. Final GPU results come from the isolated repeat with the controller paused and a GPU-memory check before each model. See [correction record](isolation_correction.json). API controls reuse their original calls.

## Quality

89 independent cases, each in original and reversed candidate order: 178 quality requests per model, {total} total. A multi-question case passes only if every choice matches the frozen reference. Failures remain in the denominator. These are **reference-policy matches**, not general accuracy or official JevBench scores.

{table(["Model", "Payment steps", "Routing", "Device actions", "Temperature sets", "Call/format failures"], quality_rows)}

Payment uses 40 snapshots: four scenarios × pending/ready × five stages, with the same optimized input for every model. Later snapshots follow the reference trajectory; this is not an autonomous transaction rollout. Routing reuses 32 frozen validation cases with catalogue facts and synthetic endpoint conditions; no selected downstream model is invoked. Device cases contain three decisions over power, integer temperature and mode. The five temperature-set cases use 15 independent binary questions for all models.

References are used only for offline grading. See [inputs](requests.json), [references](references.json), and [frozen plan](plan.json).

### Task classification versus constrained model selection

{table(["Model", "Task-profile routing", "Capabilities", "Cost/budget", "Availability/fallback/preferences"], routing_rows)}

Strands, Liquid, Perplexity, KnowLine and Jev match all 16 task-profile observations. GPT requests missing material in five cases where the task description says source code, a trace or a proof is supplied. This benchmark asks which workflow should handle that description, without executing the downstream task. These differences reflect interpretation of the task boundary; they should not be read as a universal intelligence ranking.

## Latency

Median successful quality-request latency in milliseconds. Requests contain one, three or fifteen decisions.

{table(["Model", "Payment", "Routing", "Three device decisions", "Fifteen temperature decisions"], latency_rows)}

GPU calls use loopback on the inference host. API calls include network round trips from a us-east-1 development EC2. These are service-request measurements, not directly comparable pure GPU compute times.

Strands uses its original SDK. Liquid uses its official Transformers implementation. Perplexity uses `fast=False`. KnowLine uses its official HF BF16 fallback with read-twice, not the recommended SGLang FP8 deployment. The latter two lack the optional fast convolution and linear-attention kernels. H2O uses vLLM 0.30.0 with its pinned Python overlay, bidirectional attention, eager execution and an 8192-token context. These runs do not establish each model's optimized performance ceiling.

<details>
<summary>Warmed concurrency 1 / 4 / 8 results</summary>

Every level runs the same eight cases four times: 32 requests and 160 decisions. Model loading is excluded. P50/P95 include valid responses; throughput is valid requests divided by whole-batch elapsed time, not tokens/second. Strands, Liquid, Perplexity and KnowLine wrappers serialize CUDA execution, so concurrency adds queues rather than demonstrating their maximum batching capacity.

{table(["Model", "Concurrency", "P50 ms", "P95 ms", "Valid requests/s", "Valid responses"], perf_rows)}

[Machine-readable performance metrics](results/performance_summary.json).

</details>

## Actual choices and business effects

Original-order examples: (1) fully paid 129 USDC with 12/12 confirmations, expected `credit_order`; (2) reduce the current 26°C setting by two degrees, expected `24`; (3) route a supplied connection-pool deadlock debugging request, expected `code_analysis`.

{table(["Model", "Credit execution", "Target temperature", "Debugging workflow"], example_rows)}

Strands selects `hold` in this credit sample. `JSON error` means strict parsing failed; responses were not silently repaired or retried.

We also apply each payment choice to its independent frozen sandbox snapshot and compare final device settings:

{table(["Model", "Payment guard corrections", "Simulated ledger entries/8 opportunities", "Hard route violations/48", "False no-route/48", "Device final states/24"], audit_rows)}

These ledger entries are **independent simulated steps**, not real transfers or completed model-driven transaction rollouts. Eligible-but-not-preferred routes are recorded separately in [business_audit.json](results/business_audit.json). Devices start off, set to 26°C and heat mode. Final-state grading allows setting an already-current value to be equivalent to leaving it unchanged; strict action grading retains that difference.

## Liquid native multi-select

With `type: "choice", multiple: true` and all 15 integer candidates from 16 through 30, {native_correct}/{len(native)} cases match the exact requested set. Loopback latency is {native_range} ms. The inclusive range 22–25 returns `["22","23","24","25"]`; other cases cover explicit sets, exclusions and the empty set. This extra capability test uses original candidate order and is excluded from the paired quality table.

[Exact requests](liquid_native_multiselect.json) · [actual responses](results/liquid-native-multiselect.jsonl)

## Candidate-order sensitivity

{table(["Model", "Changed cases / pairs with two valid responses"], flip_rows)}

The two orders are repeated observations of the same cases. For API models, differences may also include service numerical variation or generation randomness; this experiment does not attribute every change solely to position bias. GPT has fewer valid pairs because of formatting failures.

## Recommendations by use case

- **Local deployment with stronger reference adherence: H2O-Lightning 4B.** Payment 80/80, routing 54/64 and 161/178 exact cases are the best local-model results in this batch. Payment median is 93 ms. Seven hard-constraint violations in 48 constrained routes still require attention.
- **Low latency, device actions and multi-select: Liquid d1-2B.** Payment is 77/80 at a 39 ms median; three device decisions take 61 ms; native set selection passes 5/5. Complex routing remains weak at 35/64, including 23/48 hard-constraint violations.
- **Another payment candidate: Perplexity Flash.** Payment 80/80, all eight simulated ledger opportunities, and 145 ms median payment latency. Routing is 47/64; its current reference inference path is not a speed ceiling.
- **Final device settings: retain KnowLine for further comparison.** Strict actions match 19/24 and final states 23/24; payment is 80/80. The HF path is slower, with an 852 ms device median; test the recommended deployment before judging suitability for frequent calls.
- **Existing Strands: task-profile routing and validated local choices.** Task classification is 16/16 and median payment latency 65 ms, while payment reaches 66/80 and full routing 26/64. Clarify the scope of conditions, add counterexamples and explicit completion criteria, then evaluate fine-tuning on a held-out set. This round does not measure those proposed improvements.
- **Hosted API: Jev has the strongest overall reference adherence here.** It reaches 169/178, with payment/routing medians of 75/87 ms and 91.42 valid requests/s at concurrency eight. GPT matches all 48 constrained-routing observations, with payment/routing medians around 0.92/1.02 seconds, but has 12 quality-response format failures.

GPT uses a prompt-only JSON contract, without constrained structured decoding. Two payment and ten device responses fail strict parsing; the raw outputs are retained. Improve the output contract and retest before attributing those failures to reasoning ability. GPT matches 161/166 valid responses; the primary table still includes all 178 attempts.

These conclusions apply to these frozen inputs. Budget arithmetic, condition scope, missing-material interpretation and no-change semantics need business-specific checks; this is not a universal intelligence ranking.

## Evidence and reproduction

The original text model, vision service, GPU controller and schedule were restored after testing, with the instance left running. Temporary model environments and S3 installation artifacts were removed; measurement evidence is retained. See [restoration record](restoration.json).

[Quality summary](results/summary.json), [mismatches](results/mismatches.json), [raw results](results/), [pinned models and hashes](models.json), [hardware](hardware.json), and [order-preserving request hashes](ordered_request_hashes.json).

`prepare.py` freezes inputs; `run.py` calls providers and parses strictly; `analyze.py`, `business_audit.py` and `performance.py` grade offline. `gpu_server.py` wraps official implementations, and `trial.py` runs and terminates one model. Offline provisioning and temporary-control helpers are in this directory; credentials and signed manifests remain in ignored `.deployment/` files.

```bash
python -m unittest discover -s validation/open_decision_models -p 'test_*.py'
python validation/open_decision_models/analyze.py
.venv/bin/python validation/open_decision_models/business_audit.py
python validation/open_decision_models/performance.py
python validation/open_decision_models/report.py
```

Selection references: [JevBench](https://benchmarkheaven.com/jev-models), [API/methodology](https://benchmarkheaven.com/jev-models/api), and the [Liquid](https://huggingface.co/LiquidAI/d1-2B), [Perplexity](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2), [KnowLine](https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5), and [H2O](https://huggingface.co/h2oai/h2o-lightning-4b) model cards. This is not a full JevBench run; external leaderboard scores are not mixed into business results.
"""
    (ROOT / "README.zh.md").write_text(zh)
    (ROOT / "README.md").write_text(en)


if __name__ == "__main__":
    main()
