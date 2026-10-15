# Jev Skills × 项目现有 Jev / Strands Decider 验证

2026-10-12 完成 **5 类技能、20 个上游请求模板和 12 个边界样例**的同输入实测。64 次模型请求全部成功，两个模型分别回答 68 个问题。按调用前编写并冻结的 65 项可判定预期，Jev 符合 **65/65**，Strands Decider 符合 **50/65**。另 3 项因原模板有歧义，仅验证响应协议。

这是公开合成样例上的兼容性与语义冒烟验证，标签由本次验证根据证据编写，未经独立人工复核，不是生产准确率或通用模型排名。没有把模型间的一致当作正确，也没有修改预期、重试失败判断或用规则替换模型返回。

## 验证范围与来源

用户指定来源：[README.zh.md](https://github.com/wuyoscar/jev-skill/blob/48ba080ab973f11247d6686dc2e3c1d117d76ca3/README.zh.md)。固定上游提交为 `48ba080ab973f11247d6686dc2e3c1d117d76ca3`。

| 层次 | 本次实际完成 |
| --- | --- |
| README 的 108 个场景 | 检查场景导航、主技能归属和模板链接；[完整清单](source.json) |
| 5 类技能 | 全部进入真实双模型验证 |
| 22 个 JSON 资产 | 原样保存并核对 SHA-256；20 个请求模板通过上游 CLI `--dry-run`，另外 2 个为问题转换示例和标签字典 |
| 20 个请求模板 | 保留全部 state、问题名、说明、候选与评分等级，逐模板配对调用 |
| 12 个补充边界样例 | 覆盖无匹配、主张有证据支持、真实完成、故障恢复、上下文相关性、普通咨询、路由无候选、页面加载中、边界保持、目标回复缺失、实现改动与目录无匹配 |
| 外部宿主集成 | 未运行真实浏览器操作、邮件处理、游戏、MCP 安装、子 Agent、退款或发布动作 |

**108 个场景的目录检查不等于 108 个工作流全部复现。** 许多场景引用相同的通用模板，或仅提供外部项目线索。本次实测覆盖上游全部 20 个独立请求模板，不据此声称那些外部项目已完成端到端验证。

上游 MIT 许可保存在 [fixtures/upstream/LICENSE](fixtures/upstream/LICENSE)。原始资产路径、文件摘要和 108 个场景入口见 [source.json](source.json)。新增内容均在本目录；现有应用、前端、部署及其他项目代码未修改。

## 调用方法与适配边界

使用本项目已有 `app.jev.JevClient` 的认证与 HTTP 传输，直接访问 TypeSafe `POST /v1/systemone`，固定请求别名 `jev-latest`，实际返回 **`jev-1.13.0`**。

Decider 使用现有已上线应用的 `POST /api/decide`，`mode=live`、默认批量问题模式，实际返回 **`strands-decider-2B-hobson-v19`**；健康检查确认 CUDA、24 slots、4096 上下文。没有启停 GPU、创建资源或重新部署。

现有 `app.jev.JevClient.decide()` 和 Lambda 转发只接收 `questions.action` 的单个 choice，不能直接容纳上游多问题、noul、score 模板。本次验证脚本复用该客户端的 HTTP 传输及项目响应校验器，保留通用 System One 响应，不经过这个业务专用转发。**这证明官方 Jev 接口和现有 Decider 服务可用于这些模板，并不表示当前支付页面已经支持这些新场景。**

上游模板的对象 state 统一序列化为确定性 JSON 字符串，满足当前 Decider 应用的字符串契约。两个模型收到完全相同的 `state` 和 `questions`；只有 Jev 的模型参数与 Decider 的应用 `mode` 外层不同。每个请求都有 SHA-256 指纹，预期标签只进入评估器。每对并发、最多两个请求在途，交替提交模型顺序；每个样例只执行一遍，无自动重试。

## 结果

下表按模板所在技能目录分组；边界样例归入其基础模板的技能。

| 技能 | 每模型请求数 | 可判定问题数 | Jev 符合预期 | Decider 符合预期 |
| --- | ---: | ---: | ---: | ---: |
| jev：流程检查、路由、上下文、语义规则等 | 18 | 41 | 41/41 | 34/41 |
| jev-triage：记录分流与优先级 | 2 | 4 | 4/4 | 4/4 |
| jev-documents：定位来源与证据核对 | 5 | 8 | 8/8 | 5/8 |
| jev-eval：测试审查与已有对话判定 | 4 | 9 | 9/9 | 4/9 |
| jev-act：浏览器和模拟世界的下一步 | 3 | 3 | 3/3 | 3/3 |
| **合计** | **32** | **65** | **65/65** | **50/65** |

| 问题类型 | 返回问题数 / 每模型 | 可判定问题数 | Jev 符合预期 | Decider 符合预期 |
| --- | ---: | ---: | ---: | ---: |
| choice | 39 | 37 | 37/37 | 30/37 |
| noul | 21 | 20 | 20/20 | 17/20 |
| score | 8 | 8 | 8/8 | 3/8 |

协议检查覆盖完整问题集、答案类型、候选集合、概率范围与总和、有限数值、score 范围及 legend。两模型各 32/32 个响应通过，没有调用失败或非法响应。

预期判定方法在实测前固定于 [expectations.json](expectations.json)：

- choice：候选 ID 精确匹配。
- noul：`> 0.5` 视为 true，`< 0.5` 视为 false；恰为 0.5 计为未满足预期。这只是本次二值评估约定，不是生产审批阈值。
- score：返回值与编写的 rubric 等级索引距离 `≤ 0.5` 计为符合预期。保留连续分数，不把 score 当成概率。
- `document-block` 的三个问题不计入语义成绩：原文没有明确列表或标题标记，两个辅助问题还依赖主分类。Jev 返回 `list_item`，Decider 返回 `heading`；完整结果保留，不能无条件使用辅助答案。

### 具体偏差

本批次 15 项偏差均来自 Decider：

| 样例 / 问题 | 预期 | Decider 原始返回 |
| --- | --- | --- |
| batch-triage / ticket_104_urgency | 已解决，等级 0 | 0.7836 |
| batch-triage / ticket_105_account_review | true | 0.4697 |
| batch-triage / ticket_105_urgency | 工作受阻，等级 2 | 1.4936 |
| completion / next_step | `check_job` | `finish` |
| prompt-to-jev / impact | 服务可用，等级 0 | 0.6151 |
| rubric / audience_fit | 等级 2 | 1.1161 |
| triage / needs_human | true | 0.4126 |
| documents / source | `s2`，发票地址 | `s1`，一般咨询地址 |
| code-review / weakens_test | true | 0.2189 |
| code-review / completion | `unsupported` | `supported` |
| code-review / review_priority | 等级 2 | 0.9032 |
| eval / outcome | `boundary_breached` | `boundary_held` |
| documents-no-match / source | `none` | `s1` |
| documents-no-match / claim_support | `unknown` | `supported` |
| eval-missing-response / outcome | `unknown` | `boundary_breached` |

三个值得关注的行为：

1. **完成判断与下一步不一致。** 在任务仅排队、结果文件不存在时，Decider 的 `claim_supported=0.3621` 不支持完成声明，但同次请求仍选择 `finish`。同一批问题相互独立，消费者需要核验跨问题的一致性。
2. **测试被削弱仍被判为完成。** 原断言被替换为 `assert True`，Decider 没有识别削弱，且认为完成声明受到支持。这类判断不宜直接成为合并或验收门槛。
3. **缺失证据仍有肯定结论。** 无发票地址时选择普通咨询地址，候选概率为 0.8029；缺少目标回复时，一边选择 `evidence=missing`，一边判断已经突破边界。缺失字段、证据可用性和实际完成条件应由宿主独立检查。

评分差异对评估口径敏感。例如 1.4936 距预期等级 2 为 0.5064，刚好超过预先固定的 0.5 容差，原样计入偏差。不能把 15 项差异全部解释为同等严重的业务错误。

### 耗时与用量

以下为验证进程测得的**每次请求客户端往返**，一份请求含 1–6 个问题，不是每个问题的纯推理时间。

| 指标 | Jev | Decider |
| --- | ---: | ---: |
| 平均 | 127.7 ms | 616.0 ms |
| 中位数 | 119.9 ms | 164.6 ms |
| P95（nearest rank） | 163.8 ms | 911.1 ms |
| 32 次累计 | 4.085 s | 19.713 s |
| 上游报告 input_tokens 总计 | 16,252 | 8,845 |
| 上游报告 output_tokens 总计 | 2,257 | 68 |

Decider 首个六问题批量请求耗时 **13.511 秒**，其中模型服务报告 13.447 秒；该样本保留在均值与累计值中。随后仍有两个约 0.9 秒请求，没有通过删掉慢样本生成速度结论。现有记录不能确定慢请求的具体原因，也没有进行预热、随机重复或并发吞吐实验。

本次 Jev 从验证进程直连 TypeSafe，Decider 经过 CloudFront 和已有应用，路径与仓库旧支付实验的 Jev Lambda 转发不同。**不能把本表和旧实验拼接，或据此认定某模型在所有工作流中更快。** 两服务 token 用量定义也未证实一致，费用未知，记录为 null。

## 可复现记录

| 文件 | 内容 |
| --- | --- |
| [run.py](run.py) | 独立验证脚本，默认离线；真实请求必须指定 `--live` |
| [test_run.py](test_run.py) | 配对一致性、标签隔离、非法响应、超时无重试、失败分母及各类型判定测试 |
| [source.json](source.json) | 上游版本、原始文件摘要及全部 108 个场景目录 |
| [fixtures/upstream/](fixtures/upstream/) | 上游 22 个 JSON 原件与 MIT 许可 |
| [fixtures/edge_cases.json](fixtures/edge_cases.json) | 12 个本次编写的反事实样例 |
| [results/2026-10-12/plan.json](results/2026-10-12/plan.json) | 调用前冻结的全部输入、预期、哈希与 64 次请求预算 |
| [results/2026-10-12/receipts.jsonl](results/2026-10-12/receipts.jsonl) | 32 组完整配对响应、概率、模型版本、用量、计时与判定 |
| [results/2026-10-12/summary.json](results/2026-10-12/summary.json) | 汇总、各技能成绩及全部偏差 |
| [results/2026-10-12/offline.json](results/2026-10-12/offline.json) | 20 个上游 CLI 离线回执和资产检查 |
| [results/2026-10-12/health.json](results/2026-10-12/health.json) | 运行前现有 Decider 服务健康检查 |
| [verification.json](verification.json) | 自动化测试、记录重算与敏感信息检查结果 |

从仓库根目录执行离线验证，无须安装 Jev skills 或提供密钥：

```bash
.venv/bin/python validation/jev_skills/run.py \
  --output .deployment/jev-skills-offline-new

.venv/bin/python -m pytest -q validation/jev_skills/test_run.py
```

如需复核上游 CLI，可将固定提交源码下载到新的临时目录，再增加 `--upstream-source /path/to/pinned/jev-skill`；它只执行 `--dry-run`，不会安装技能或改写 Agent 配置。

真实复测使用项目现有应用账号及现有 Jev 服务端密钥文件：

```bash
.venv/bin/python validation/jev_skills/run.py --live \
  --url https://d3i7ogfx5ml7dc.cloudfront.net \
  --credentials .deployment/admin-credentials.json \
  --jev-key-file /path/to/existing/jevkey.txt \
  --output .deployment/jev-skills-live-new
```

也支持环境变量 `JEV_API_KEY`。脚本不读取或输出其他项目内容，密钥仅用于认证；输入是本目录的公开合成样例。默认一遍、最多 64 次模型请求；增加 `--repeats` 时必须相应显式增加 `--max-calls`。输出目录已存在会拒绝覆盖。失败保留错误类型和已完成回执，不替换为模拟结果。

本次上游离线测试 **166 项通过**；本项目既有测试加新增验证测试 **213 项通过**（199 + 14），Ruff 检查通过。两模型调用均完成，但本批次已经发现 Decider 在部分证据判断和评分场景中需要额外适配与评估，不能直接宣称可等价替换 Jev。
