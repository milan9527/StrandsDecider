# Liquid d1-2B 空调 LoRA 微调实测

测试日期：2026-11-01。状态：本轮完成。报告生成时间：2026-11-01T01:46:53.670160+00:00。

**新表达测试集完整正确数：0/192 → 157/192。预定相对改进门槛全部通过，尚未部署到生产。**

原规范三轮的一次全答完整正确率从 0% 提升到 90%，平均耗时 0.657 → 0.657 秒。微调后的 30 步串行正确率为 80%，平均 3.467 秒。本轮结果支持优先使用原生一次全答路径；LoRA 合并后提高准确率，推理耗时基本保持。相对改进门槛通过不代表生产验收通过，剩余漏发和多发仍需处理。

本轮训练 Liquid 的原生候选选择能力，保留完整输入、30 个字段和 283 个候选。没有改成生成 JSON、没有增加 Pointer Head、没有压缩输入、筛选候选或事后修复命令。所有正式微调成绩均来自合并到 BF16 权重后的官方 system_one 推理路径。

## 数据与训练

1,024 条训练请求、96 条验证请求、192 条新表达测试请求，均为按规范能力构造的合成数据，中英文各半。先生成动作意图，再生成表达和完整标签；不使用教师模型。不同分区使用不同的“执行动作＋明确保持不变功能”条件组合及表达模板，但共享词汇和生成器，属于同领域合成留出测试，不是外部盲测，也不能替代真实用户分布验证。

若只按最终执行命令集合比较，新测试中有 28/192 条的命令集合也出现在训练集，只是保持不变的条件和表达不同。因此不能把整个新测试集称为未见动作组合测试。

本轮从全部合法取值构造动作，数值范围字段在合成数据中占比较高，训练和新测试覆盖全部 30 字段，验证集实际执行覆盖 29 字段。因此同时单列原规范及历史扩展表现，不能只用合成集总正确率判断实际应用效果。

原规范及历史扩展共 78 条查询不进入训练，另作回归。训练和验证标签可供训练进程读取；新测试与历史标准答案仅在本机离线评分。测试导出只包含题号、请求和语言，含标签信息的组合元数据不上传。全部输入、划分及采用条件在正式训练前冻结。

固定模型 LiquidAI/d1-2B，revision `cfe5760ff5d5998f91d9ac56bd4b2dbd96996d41`。仅文本注意力 q_proj/v_proj 加入 LoRA，共 1,171,456 个可训练参数；基础权重、视觉部分、输入嵌入和输出层冻结。r=16、alpha=32、dropout=0.05，AdamW 学习率 5e-5、梯度累积 16、训练一轮。

正式训练共 64 次优化器更新，训练及中间验证用时 39.9 分钟，不含初始基线验证、模型加载和后续完整测试。所选适配器为 `validation/ac_control/runs/2026-11-01-liquid-lora-v1/training/adapter-1024.pt`，SHA-256：`2a87384a624545021fc6ca91cf5406ed42e518a8607f048ca264048f57a0d171`。

LoRA 使用标准 W + (alpha/r)BA 参数化，A 为 Kaiming 初始化、B 为零初始化，适配器以 FP32 保存，前向计算转为 BF16。实现为本实验的显式线性层包装，未声称使用官方 d1 训练脚本或 PEFT Trainer。

训练按官方 set_size=16 编码，每个完整请求的两个问题组分别反向传播，累计同一任务的损失。随机排列字段及选项，同步更新正确选项位置。对执行字段和省略字段分别平均交叉熵后各占一半；全部省略的样本使用省略字段均值。官方候选别名最大值评分保留在可求导的 Torch 运算中。

梯度验证通过：8 次更新损失 0.3463 → 0.1387，训练评分与官方选择一致，原权重未更新。正式训练从原始权重和新初始化 LoRA 开始，没有继承梯度验证的适配器。

按验证集完整正确数选择训练 1024 条后的检查点。正确数相同时依次比较多发加漏发数量及更早检查点；不使用测试成绩换模型或继续调参。

| 检查点 | 验证正确 | 多发 | 漏发 |
|---|---:|---:|---:|
| 原模型 | 0/96 | 560 | 5 |
| 256 条后 | 59/96 | 47 | 14 |
| 512 条后 | 63/96 | 36 | 12 |
| 1024 条后 | 76/96 | 19 | 8 |

## 准确率

heldout 是新合成留出集；spec 是原规范；extension 是历史扩展；validation 是历史英文回归集，不是选检查点的 96 条 dev 验证集；chinese 是历史中文回归集。

| 数据集／候选顺序 | 原模型完整正确 | LoRA 完整正确 | 原模型多发／漏发 | LoRA 多发／漏发 |
|---|---:|---:|---:|---:|
| heldout/original | 0/192 | 157/192 | 1192/5 | 46/4 |
| heldout/reversed | 6/192 | 159/192 | 682/7 | 40/4 |
| spec/original | 0/20 | 18/20 | 105/0 | 1/1 |
| spec/reversed | 0/20 | 18/20 | 73/0 | 1/1 |
| extension/original | 0/10 | 9/10 | 60/0 | 1/1 |
| extension/reversed | 0/10 | 7/10 | 41/0 | 2/2 |
| validation/original | 0/24 | 20/24 | 150/0 | 4/0 |
| validation/reversed | 0/24 | 22/24 | 104/0 | 1/1 |
| chinese/original | 0/24 | 17/24 | 174/2 | 4/4 |
| chinese/reversed | 0/24 | 19/24 | 118/3 | 4/5 |

完整命令集合严格匹配：任何多发、漏发或错值均判整题失败。“多发”统计错误输出的命令，“漏发”统计未正确输出的目标命令；字段值选错会同时计入两项。原序和倒序是同一批查询的两个条件，不算新的独立问题。

改善主要来自减少多发命令。历史中文回归中，原序漏发从 2 增至 4，倒序从 3 增至 5；原规范也仍有一条显示灯关闭命令漏发。完整正确率改善不能掩盖这些执行字段退化。

| 原规范类别（原候选顺序，一次全答） | 原模型 | LoRA |
|---|---:|---:|
| 单指令 | 0/10 | 9/10 |
| 多指令 | 0/10 | 9/10 |

## 具体选择示例

以下为原规范、原候选顺序、一次全答的真实输出；只列非省略字段。

### S01：Turn on the air conditioner.

- 标准命令：`{"t_power":"1"}`
- 原模型：`{"t_power":"1","t_swing_angle":"0","t_swing_follow":"0","t_8heat":"1","t_outdoor_selfclean":"1"}`
- LoRA：`{"t_power":"1"}`

### S09：Turn off the air conditioner display light.

- 标准命令：`{"t_dimmer":"0"}`
- 原模型：`{"t_power":"0","t_fan_mute":"0","t_swing_angle":"0","t_swing_follow":"0","t_8heat":"0","t_dimmer":"0","t_outdoor_selfclean":"1","t_tms":"0","t_outdoor_mute":"0","t_dr_mode":"0"}`
- LoRA：`{}`

### M08：Turn on up-and-down swing and set the horizontal airflow to both sides.

- 标准命令：`{"t_up_down":"1","t_swing_direction":"2"}`
- 原模型：`{"t_up_down":"1","t_left_right":"1","t_swing_angle":"0","t_swing_direction":"2","t_swing_follow":"0","t_outdoor_selfclean":"1"}`
- LoRA：`{"t_up_down":"1","t_swing_angle":"0","t_swing_direction":"2"}`

S09 仍把关闭显示灯省略；M08 仍多发 `t_swing_angle=0`。这两类错误需要后续补充真实表达及相近功能的区分样本，本轮没有使用测试答案继续训练。

## 原规范 20 题 × 三轮：准确率与耗时

| 方式 | 原模型 | LoRA |
|---|---|---|
| 实测单字段 | 1470/1800；115.6 ms | 1788/1800；115.5 ms |
| serial30 | 3/60；平均 3.469 s，P95 3.508 s | 48/60；平均 3.467 s，P95 3.503 s |
| full30 | 0/60；平均 0.657 s，P95 0.663 s | 54/60；平均 0.657 s，P95 0.663 s |

同一 us-east-1d g6.xlarge/L4，原模型和合并后的微调模型同时常驻，所有外部调用严格串行，配对任务交替先后顺序。使用相同软件、精度、输入和推理接口。正式耗时包含 loopback HTTP 与 SDK，模型加载、检查点验证、预热、写盘和上传不计入。单步时间来自实际单字段调用，不用整任务除以 30。单字段正确率包括大量应当省略的字段，不能等同于整条用户指令正确率；三轮重复用于测量耗时，也不是 60 条不同的测试指令。

## 保存、重载与采用判定

独立评估进程重新加载适配器；再次加载的 8 条验证探针输出一致。合并及恢复原生投影融合后，0 条探针选择变化；最大概率差 0.020920。最终完整质量测试覆盖合并后的实际模型，不能假定 BF16 合并必然数值等价。

保留原模型的概率温度配置，没有重新校准微调后的置信度。本轮只验收候选选择和命令集合，不把返回概率视为已验证的正确率，也不使用置信度阈值过滤输出。

| 预定门槛 | 通过 |
|---|---|
| heldout_original_exact_improved | 是 |
| heldout_original_active_not_worse | 是 |
| spec_original_not_worse | 是 |
| heldout_reversed_exact_improved | 是 |
| heldout_reversed_active_not_worse | 是 |
| spec_reversed_not_worse | 是 |
| full30_mean_within_10pct | 是 |
| full30_p95_within_10pct | 是 |
| zero_errors | 是 |

全部质量条件中，原先正确而微调后错误的条件有 0 个。总准确率改善不代表每题都改善；逐题变化保留在证据中。

## 证据

共 4,862 次实际推理 HTTP 调用，接口错误 0 次，请求无重叠。README 保持不变，EC2 保持运行。

- [冻结计划](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/plan.json)
- [数据审计](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/data-audit.json)
- [测试输入导出审计](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/evaluation-export-audit.json)
- [字段覆盖与划分核查](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/data-coverage.json)
- [训练与测试命令集合重叠](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/split-limitations.json)
- [检查点选择](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/training/selection.json)
- [完整汇总](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/summary.json)
- [逐题评分](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/scored.json)
- [选择变化](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/choice-changes.json)
- [示例原始选择](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/examples.json)
- [重载与合并](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/evaluation/reload-merge.json)
- [推理审计](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/audit.json)
- [最终 EC2 状态](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/final-environment.json)
- [原始请求回执](../validation/ac_control/runs/2026-11-01-liquid-lora-v1/evaluation/receipts.jsonl)

发布说明：计划与审计中的 GitHub 状态、README 哈希记录测试结束时的状态。本次按用户要求发布报告与测试证据，并更新主 README 的选型摘要。训练适配器保存在本地和 EC2，仓库发布训练配置与结果，适配器文件不随本次文档提交上传。
