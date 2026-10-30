# 空调控制选择测试

依据 [AC_Control_Test_Spec.md](../../docs/AC_Control_Test_Spec.md)，真实调用 EC2 上已部署的 Strands Decider v19，评估英文 Query 到完整空调 `cmdList` 的选择。

阅读入口：[五模型测试总结、优化建议与结论边界](../../docs/AC_CONTROL_COMPARISON.md)。

延迟复核：[单任务与逐Key串行补测](runs/2026-10-30-serial-latency-v1/LATENCY.zh.md)。原测试已按空调Query串行、三个GPU模型依次运行；每条Query含30个选择题。补测独立单Key平均 Decider **97.3 ms**、Liquid **105.8 ms**、H2O **200.5 ms**，逐Key串行完成30题为 **2.93 / 3.18 / 6.02秒**。同一S03输入、每模式3轮、279次正式调用全部成功且无重叠。Liquid拆分后每轮6个Key选择改变，原准确率仍属于完整30题封装，不能与单题诊断混用。

最新：[加入Jev与GPT 6.1 Sol low的五模型实测](runs/2026-10-30-api-ablation-v1/FIVE_MODELS.zh.md) · [错误定位、完整问题选项与实际回答](runs/2026-10-30-api-ablation-v1/DIAGNOSTICS.zh.md)。Jev使用原生API，返回 `jev-1.14.0`；GPT使用Bedrock `us.openai.gpt-6.1-sol`，每次显式设置low effort。新增两个模型各250条观察，业务输入与参考沿用已冻结对照；原三个模型复用750条已核验观察。

原规范20题、原始候选顺序的整条指令完全匹配：

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---:|---:|---:|---:|---:|
| Strands Decider | 4/20 | 1/20 | 3/20 | 1/20 | 0/20 |
| Liquid d1-2B | 0/20 | 1/20 | 6/20 | 4/20 | 11/20 |
| H2O Lightning 4B | 18/20 | 18/20 | 19/20 | 18/20 | 20/20 |
| Jev 1.14.0 | 19/20 | 19/20 | 20/20 | 20/20 | 20/20 |
| GPT 6.1 Sol · low | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |

另10条诊断题，Jev与GPT五组均为10/10。Jev基线唯一错误是M08额外输出 `t_swing_angle=0`；明确规则后消失，不需要两阶段才能达到本批满分。GPT基线已全部正确；两阶段主结果平均客户端耗时3.040→4.548秒，没有准确率收益。Jev仅改规则约0.106秒、两阶段0.133秒。计时包含各自API路径与缓存状态，不能视作纯模型计算速度；本批小样本不等同生产可靠性。

新增600次正式调用尝试中，599次有完整返回证据。GPT第180条（M08、反转顺序、仅改选项）因SDK bytes保存失败丢失结果，保留为采集失败、未重跑；该组换序按19/20计，其余保存的GPT回答全部正确。原始顺序主结果不受影响。仅修复日志编码后继续后70条，旧证据未修改；[最终核验](runs/2026-10-30-api-ablation-v1/audit.json)明确记录这一缺口。17项检查通过，完整复现及故障续跑说明见下文。

以下保留此前三模型实验与基线记录。

新增 [三模型提示词与两阶段对照](runs/2026-10-30-prompt-ablation-v1/ABLATION.zh.md)，以及[门控诊断、完整请求和实际回答示例](runs/2026-10-30-prompt-ablation-v1/DIAGNOSTICS.zh.md)。下表为原规范20题、原始候选顺序的整条指令完全匹配，不含程序补单位：

| 模型 | 原始基线 | 仅改选项条件 | 仅改规则与问题 | 两项合并 | 两阶段 |
|---|---:|---:|---:|---:|---:|
| Strands Decider | 4/20 | 1/20 | 3/20 | 1/20 | 0/20 |
| Liquid d1-2B | 0/20 | 1/20 | 6/20 | 4/20 | 11/20 |
| H2O Lightning 4B | 18/20 | 18/20 | 19/20 | 18/20 | 20/20 |

两阶段改善了 H2O 和 Liquid 在原规范的成绩，但 Decider 在第一步全部选择 omit。Liquid 的多余指令由105条降至2条，同时新增8条缺失指令；不能只看多余指令减少。H2O 两阶段换序仍为20/20，输出全部不变；仅改规则能修复摆风重复编码，合并改写又出现该错误。提示词更长、组合更多改写，并不保证更好。每例服务端平均耗时：Liquid 两阶段约0.741秒，H2O约7.100秒；各部署的计时与处理方式不同。

另计的10条新表达与反例中，基线→两阶段：Decider **0→0/10**、Liquid **0→5/10**、H2O **10→9/10**。H2O 两阶段把“关闭室内静音”额外解释成关闭舒适自动，因此不能视作全面优于基线。新增诊断题是在看过旧基线错误后设计、在本轮推理前冻结的，不是独立盲测集。本轮新增630条正式观察、725次HTTP调用，全部返回有效结果；另外复用120条历史基线观察。输入、响应、源码、模型身份与服务未重启状态均通过[最终核验](runs/2026-10-30-prompt-ablation-v1/audit.json)。

新增 [Liquid / H2O / Decider 同输入比较](runs/2026-10-30-resident-v1/COMPARISON.zh.md)。Liquid 和 H2O 各新增 40 次正式调用；Decider 复用下方同日基线。请求、候选顺序和评分规则一致，原始证据分别保留。

这套输入下 **H2O 最好：单指令 9/10、多指令 9/10，合计 18/20**；换序仍为 18/20，全部 20 条输出保持不变。它选全了参考中的 40 条指令，仅额外输出 2 条：开机时加了制冷模式，上下摆风时加了 `t_swing_angle=0`。Liquid 也选全了 40 条参考指令，但额外输出 105 条，完整匹配为 0/20。原始顺序每例 30 问服务端平均耗时：Decider 2.907 秒、Liquid 0.609 秒、H2O 5.962 秒；服务端计时边界与实现不同，不能当作纯 GPU 性能比较。新增 80 次正式调用全部成功。

[2026-10-30 实测报告](runs/2026-10-30-v1/REPORT.zh.md)包含单指令、多指令、Key/Value、多余/缺失指令、耗时与逐例差异。原始顺序是主结果；候选反转是同一批用例的稳定性检查。

本轮原始顺序完全匹配 **4/20**（单指令 4/10、多指令 0/10），候选反转 **2/20**，18/20 条换序后输出改变。原始顺序 Key 召回率 **47.5%**，缺失指令 **21/40**；5 条温度用例全部漏掉单位字段。已选对的 Key 上 Value 均正确，但完整 cmdList 仍多不满足规范。40 次正式调用全部成功，每条 Query 的 30 问服务端平均 **2.907 秒**。当前输入方案不能稳定满足文档要求。

每条输入包含完整的 30 项 Command Set；转成每 Key 一个 choice，共 30 问。每题提供全部合法控制值和 `omit`。范围字段列出整个合法整数区间；本批未验证小数。按模型选择直接生成 `cmdList`，不根据标准答案修正、不额外补温度单位。能力与协议约束见报告。

模型实际为 `strands-decider-2B-hobson-v19-vllm`；当前实例 `i-0ae7eb0abcb815af3`、`g6.xlarge`、`us-east-1`。硬件与运行模式另见 [环境记录](runs/2026-10-30-v1/environment.json) 和 [本次模型与调用配置](../../docs/AC_CONTROL_COMPARISON.md#实际模型与调用路径)。本测试不启停或部署模型，不向真实设备下发控制。

## 复现

在项目根目录使用已安装 `httpx` 的 Python 环境。每次使用新输出目录；脚本拒绝覆盖既有输入或正式响应。

```bash
.venv/bin/python -m pytest -q validation/ac_control/test_evaluation.py

.venv/bin/python validation/ac_control/prepare.py \
  --output validation/ac_control/runs/YOUR_RUN

# 密钥文件必须由现有部署提供，内容为 {"api_key":"...", "endpoint":"https://..."}。
# 密钥只放 Authorization 请求头，不写入测试结果。
.venv/bin/python validation/ac_control/run.py \
  --run validation/ac_control/runs/YOUR_RUN \
  --credentials /path/to/private/api-credentials.json --probe

.venv/bin/python validation/ac_control/run.py \
  --run validation/ac_control/runs/YOUR_RUN \
  --credentials /path/to/private/api-credentials.json

.venv/bin/python validation/ac_control/analyze.py \
  --run validation/ac_control/runs/YOUR_RUN
```

也可使用已有环境变量 `DECIDER_VLLM_API_KEY`，省略 `--credentials`，并传入 `--endpoint https://d1e9udi8st2p3g.cloudfront.net`。评分步骤完全离线，可单独重跑。

## 文件

- `prepare.py`：从规范提取 Query、完整 Command Set、离线标准答案，生成两种顺序的请求及 SHA-256。
- `run.py`：只读取请求，不读取标准答案；单客户端串行发出 40 次正式 HTTP 请求（1,200 个独立 choice），另有一次 30 问预检。
- `analyze.py`：严格解码、集合比较、指标及中文报告；失败留在分母，温度单位缺失不会自动修补。
- `test_evaluation.py`：验证完整候选与能力保留、答案隔离、换序等价、错误计数和不修复输出。
- `runs/2026-10-30-v1/`：冻结输入、标准答案、原始响应（含概率）、模型身份、计时、逐例评分与报告。

计划中的源码哈希记录准备输入时的版本；每轮调用额外记录实际 runner 哈希，评分记录实际 scorer 哈希。本次预检后仅调整 runner 的 import 空行以通过 lint，正式模型输入哈希保持不变；评分逻辑在正式推理前完成，环境记录链接随后加入报告。

## Liquid 与 H2O 复现

`run_resident.py` 在现有 GPU 主机上直接调用 Liquid `:18801` 和 H2O `:18803` 原生接口，绕过业务网关的 16 问/32 候选封装限制，不改变模型配置。`remote_resident.py` 通过现有部署的 SSM 与私有 S3 传输只包含请求的测试包；标准答案保留在本机。实例角色沿用已有 `input/*` 读取与 `output/*` 写入权限。

以下操作需要已有部署的 AWS 权限；默认读取相邻 `StrandsDeciderVLLM/.deployment/state.json`，也可通过 `--deployment-state` 指定。先检查预检为 Success 且每个模型返回完整 30 问，再发起正式运行。正式阶段 Liquid 跑完后再跑 H2O，完成后收集并离线评分。

```bash
.venv/bin/python -m pytest -q validation/ac_control

.venv/bin/python validation/ac_control/remote_resident.py start \
  --source validation/ac_control/runs/2026-10-30-v1 \
  --output validation/ac_control/runs/YOUR_COMPARISON

.venv/bin/python validation/ac_control/remote_resident.py collect \
  --output validation/ac_control/runs/YOUR_COMPARISON

.venv/bin/python validation/ac_control/remote_resident.py formal \
  --output validation/ac_control/runs/YOUR_COMPARISON

.venv/bin/python validation/ac_control/remote_resident.py collect \
  --output validation/ac_control/runs/YOUR_COMPARISON

.venv/bin/python validation/ac_control/compare_resident.py \
  --baseline validation/ac_control/runs/2026-10-30-v1 \
  --run validation/ac_control/runs/YOUR_COMPARISON
```

`collect` 返回 `InProgress` 时只记录状态，任务完成后再收集。两模型的有效响应必须保持模型身份、全部问题 ID 和合法候选；不自动重试、不纠错。H2O 的服务端耗时位于 `usage.latency_ms`。客户端网络路径与先前 Decider 的 HTTPS 不同，不能直接以客户端时间比较速度。

本次比较计划保存在 `comparison_plan.json`；`comparison_results.json` 可逐条查看三个模型的实际指令与差异，`comparison_summary.json` 提供完整数值。测试还验证新评分器能逐条复现原 Decider 评分结果。

## 提示词与两阶段对照复现

`prepare_ablation.py` 固定五组：原始基线、仅改候选条件、仅改规则与问题、两项合并、两阶段。原规范20题各测两种候选顺序；另有10条诊断题，只测原始顺序，单独统计。这10条是在看过基线错误后设计的，不是独立盲测集。

每模型250条观察，其中40条复用已保存基线、210条新增；两阶段先问全部30个 Key 是否适用，再对模型选择的 Key 选择 Value，两个阶段都含完整 Command Set。标准答案不上传GPU，模型输出不修复。离线单位补全只作为单独的工程指标。

```bash
.venv/bin/python -m pytest -q validation/ac_control

.venv/bin/python validation/ac_control/prepare_ablation.py \
  --output validation/ac_control/runs/YOUR_ABLATION

.venv/bin/python validation/ac_control/remote_ablation.py start \
  --run validation/ac_control/runs/YOUR_ABLATION

.venv/bin/python validation/ac_control/remote_ablation.py collect \
  --run validation/ac_control/runs/YOUR_ABLATION

# 先确认预检完成、四个新组的全部问题都获得有效返回。
.venv/bin/python validation/ac_control/remote_ablation.py formal \
  --run validation/ac_control/runs/YOUR_ABLATION

# GPU每40秒上传进度，可在运行中收集；正式完成后离线评分。
.venv/bin/python validation/ac_control/remote_ablation.py collect \
  --run validation/ac_control/runs/YOUR_ABLATION

.venv/bin/python validation/ac_control/analyze_ablation.py \
  --run validation/ac_control/runs/YOUR_ABLATION
```

远端依次运行 Decider、Liquid、H2O，全部使用GPU本机原生接口。Decider密钥由实例角色从既有Secrets Manager读取，仅用于请求头。`sources/` 保存冻结源码，`experiments.json` 保存完整第一阶段请求和第二阶段模板；各模型 `formal_receipts.jsonl` 保存每次实际HTTP请求及原始回答。输入、参考、源码和历史基线均以哈希核验。若预检失败，应保留目录证据，修正后创建新的运行目录。

运行中可用 `progress_ablation.py --run ...` 收集并显示明确标为部分结果的成绩。完成后，`audit_ablation.py --run ...` 检查请求、返回、源码、模型健康及服务是否重启；加 `--cleanup` 会先逐字节核对本地证据，再删除本轮私有S3传输对象，保留GPU目录和本地结果。`diagnose_ablation.py --run ...` 生成门控召回/漏选诊断、S03完整实际回答和原始HTTP示例。后两者不发模型推理请求，不改变提示词或正式评分。

## 加入 Jev 与 GPT 6.1 Sol low 的复现

新增API实验逐字节复用三模型对照的250份任务模板。Jev与GPT各重新运行全部250条观察，三个GPU模型复用原750条观察并重新核验原始响应评分。每模型单客户端串行，两个独立API可以同时运行；预检结果独立保存，不计入正式成绩。

Jev直接调用原生 `https://api.typesafe.ai/v1/systemone`，请求 `jev-latest`，正式响应版本固定为预检返回版本，避免应用转发层的问题数与候选数限制。密钥由已有AWS角色从部署的Secrets Manager读取，仅用于请求头。

GPT通过Bedrock Converse调用 `us.openai.gpt-6.1-sol`，每次显式传入 `reasoning.effort=low`，输出上限8192 token。固定系统提示只说明读取任务规则及JSON输出格式，不增加空调知识。未启用约束式JSON解码；只接受完整问题集合、合法的字符串候选ID，格式错误计入失败，不自动补答案或重试。模型身份依据请求modelId和保存的ACTIVE推理配置，Converse响应本身不回显模型ID。

```bash
.venv/bin/python -m pytest -q validation/ac_control

.venv/bin/python validation/ac_control/prepare_api_ablation.py \
  --source validation/ac_control/runs/2026-10-30-prompt-ablation-v1 \
  --output validation/ac_control/runs/YOUR_API_ABLATION

.venv/bin/python validation/ac_control/run_api_ablation.py \
  --run validation/ac_control/runs/YOUR_API_ABLATION --provider jev --phase probe
.venv/bin/python validation/ac_control/run_api_ablation.py \
  --run validation/ac_control/runs/YOUR_API_ABLATION --provider gpt --phase probe

# 正式运行强制检查预检已完成且无协议错误。
.venv/bin/python validation/ac_control/run_api_ablation.py \
  --run validation/ac_control/runs/YOUR_API_ABLATION --provider jev --phase formal
.venv/bin/python validation/ac_control/run_api_ablation.py \
  --run validation/ac_control/runs/YOUR_API_ABLATION --provider gpt --phase formal

.venv/bin/python validation/ac_control/analyze_api_ablation.py \
  --run validation/ac_control/runs/YOUR_API_ABLATION
```

运行中可为评分命令增加 `--partial`，它只显示部分结果，不写最终报告。正式评分同时核验旧证据未改变、冻结输入与源码、实际业务请求与模型传输参数、候选ID、两阶段选择、耗时与调用数。结果为 `FIVE_MODELS.zh.md`、`five_model_results.json`、`five_model_summary.json` 和 `audit.json`；每个API的 `formal_receipts.jsonl` 包含完整实际请求与原始返回，不包含请求头密钥。

本次 `2026-10-30-api-ablation-v1` 的GPT第180条在保存SDK对象时遇到bytes序列化错误，丢失该条返回；未重跑。原 `formal_receipts.jsonl` 保留前179条，故障日志与元数据保持不变。`resume_api_capture.py` 是针对本次中断的续跑工具，只执行尚未调用的后70条，将SDK二进制字段无损保存为带标记的Base64；业务输入、low参数及解析评分保持不变。后70条位于 `gpt/remainder_receipts.jsonl`。

本次最终评分使用以下命令，显式把缺失记录计为采集失败并保留在分母，耗时设为未知，不将它解读为模型输出了错误答案：

```bash
.venv/bin/python validation/ac_control/analyze_api_recovery.py \
  --run validation/ac_control/runs/2026-10-30-api-ablation-v1

.venv/bin/python validation/ac_control/diagnose_api_ablation.py \
  --run validation/ac_control/runs/2026-10-30-api-ablation-v1
```

故障是M08的反转顺序、仅改选项组；原始顺序主结果不受影响。`gpt/recovery_plan.json` 记录故障定位、原记录哈希及续跑范围；`audit.json` 明确区分完整原始证据与结果未知的一条记录。新增回归检查验证二进制保存不改变选择解码，以及采集缺失计失败但不虚构耗时。冻结的初版runner保留原样；它本身仍不支持SDK bytes，复现时应注意这一已知采集限制。
