# Jev / Strands Decider：真实浏览器与金融场景实测

2026-10-13 实测完成。**浏览器任务 Jev 完成 10/10，Decider 完成 4/10；金融 30 道题首轮 Jev 正确 28/30，Decider 正确 22/30。** 这组结果支持在有限动作的浏览器流程中优先试点 Jev；Decider 目前更适合简单分类和直接链接选择。两者都出现存款保险金额聚合错误，不能仅凭本轮总体分数让模型决定金融业务结果。

[打开可切换任务、并排查看截图的报告](report.html) · [机器可读汇总](runs/2026-10-13-live/scored-summary.json) · [证据完整性检查](runs/2026-10-13-live/audit.json)

## 这次实际做了什么

使用 Playwright Chromium 访问公开网站，由模型逐步选择真实 DOM 控件，执行输入、提交、点击、返回和结束。每一步都会重新读取页面文字、URL、标题、控件和最近操作，再调用模型；截图用于留证，没有作为视觉输入。模型可以浏览后续控件，每次最多给出 12 个候选动作，控件按 DOM 顺序提供，没有按参考答案排序或替模型选择下一步。

两个模型使用相同工具与任务目标，每个任务各运行两次，浏览器上下文独立，每次最多 12 步、150 秒。搜索文字由任务明确给出；输入搜索框的工具会填写后按 Enter，普通文本框则填写后按 Tab。这验证的是**有限动作、文本与 DOM 驱动的真实浏览器自动化**，还不能代表任意网页、视觉识别、登录或复杂表单的自动操作能力。

金融部分使用真实公开财报、监管政策、汇率和历史新闻。其中财报待核验陈述、存款事实和汇率处理需求由本次测试构造；未使用真实客户账户，也没有执行交易、付款或退款。

实际返回模型版本为 `jev-1.13.0` 和 `strands-decider-2B-hobson-v19`。Decider 通过现有服务访问现有 GPU，健康检查记录为 CUDA、4096 上下文长度、无视觉。共调用 **178 次**：金融 120 次、浏览器 58 次；Jev 96 次、Decider 82 次。两者均无 API 错误，无重试、回退模型或程序替选答案。总预算在运行前固定为最多 360 次。

## 真实浏览器结果

每格为成功次数 / 运行次数。成功要求：模型选择结束，且独立检查实际 URL、页面标题和正文通过；银行查询额外检查编号 628 的详情链接。

| 业务场景 | 实际任务 | Jev | Decider |
|---|---|---:|---:|
| 监管背景资料检索 | Wikipedia 搜索并打开 Basel III 文章 | 2/2 | 0/2 |
| 信用卡客服知识检索 | 从 CFPB 信用卡主页找到账单争议处理及书面通知时限 | 2/2 | 0/2 |
| 外汇资料查询 | 从 ECB 汇率主页打开美元详情页 | 2/2 | 2/2 |
| 存款保险知识检索 | 从 FDIC 保险说明页打开官方 FAQ | 2/2 | 2/2 |
| 开户前机构资质核验 | 在 FDIC BankFind 填写 JPMorgan Chase Bank，提交并查看匹配结果 | 2/2 | 0/2 |
| **合计** | **5 个任务，每模型每任务两次** | **10/10** | **4/10** |

三个有代表性的操作差异：

- **银行资质查询：** Jev 找到银行名称输入框，填写后点击 Search，结果显示两家机构，其中 JPMorgan Chase Bank, National Association 的 FDIC Cert 为 **628**。Decider 点击面包屑中的 BankFind Suite，回到入口页后直接结束，没有提交银行查询。两次都如此。
- **信用卡争议：** Jev 浏览后续控件，点击 “How to dispute a charge on your credit card bill”，到达包含 **60 calendar days** 书面通知要求的页面。Decider 点击 “Daily periodic rate”，到达信用卡术语页后结束，目标仍未完成。
- **Wikipedia 搜索：** Jev 填写 Basel III 并提交搜索，打开文章后结束；Decider 在首页直接选择结束，连搜索都没有执行。

Decider 的六次失败均为未达成目标就结束，没有点击超时或 API 故障。两次成功类型的目标链接都直接出现在第一组候选中；在这组样本中，多步检索与判断任务是否完成是更明显的薄弱环节。这里观察到的是行为差异，不能单凭这些轨迹确定模型内部原因。

Jev 也不是每次操作都最优：银行查询第一次来回浏览控件、重复填写一次，最终 **10 步**完成；第二次 **6 步**完成。它的完成率更高，但仍有操作冗余。

可直接核对：[Jev 银行查询截图](runs/2026-10-13-live/browser/fdic-bank-search-jev-2/final.png)、[Decider 银行查询轨迹](runs/2026-10-13-live/browser/fdic-bank-search-decider-2/result.json)、[Decider 信用卡错误终点截图](runs/2026-10-13-live/browser/cfpb-dispute-decider-1/final.png)。

## 金融业务结果

30 道独立题目，两个模型每题收到完全相同的状态、指令、候选和顺序。原始顺序跑完每题后，再把候选顺序反转一次；参考答案仅供评分，不进入模型输入。下面先列原始顺序，避免把重复题当成独立样本。

| 业务场景 | 来源与判断内容 | Jev 首轮 | Decider 首轮 |
|---|---|---:|---:|
| 财经资讯分流 | FinancialPhraseBank 真实新闻；正面 / 负面 / 中性 | 11/12 | 11/12 |
| 财报证据核验 | 微软 FY2025 年报；年份、单位、增长率、缺失证据 | 6/6 | 4/6 |
| 存款保险初筛 | FDIC 官方政策；合并余额、跨银行、投资产品、缺失信息 | 5/6 | 5/6 |
| 汇率报表与付款分流 | ECB 实际汇率；乘除方向、缺失币种、日期、可执行报价 | 6/6 | 2/6 |
| **合计** | **30 道题** | **28/30（93.3%）** | **22/30（73.3%）** |

反转选项后，Jev 仍为 **28/30**，Decider 为 **24/30**。合并两种顺序是 **56/60 vs 46/60**，但样本仍只有 30 道。Jev 0/30 题改变答案；Decider 2/30 题改变，都是原本正确的历史报表汇率换算，在原始候选顺序中却被判为“索取付款可执行报价”，反转后改对。

### 哪些错题影响真实业务

**财报：把另一年的数字和错误单位判成有证据支持。** 微软年报写明表格单位为百万美元，2025 年收入为 281,724，2024 年为 245,122。Decider 两种顺序下均支持错误陈述“FY2025 收入 245.122 billion”和“FY2025 收入 281.724 million”；Jev 均判为矛盾。这里不是让模型预测股价，而是审查给定证据是否支持一条财报事实。

**存款保险：两个模型都漏掉合并余额。** 同一人在同一家受保银行，持有同属 single-owner 类别的 180,000 美元支票账户和 120,000 美元储蓄账户。政策明确要求同银行、同所有权类别合并计算，合计 300,000 美元，本题本金中最多 250,000 美元受保，50,000 美元超限。两个模型、两种顺序都选择了 `fully_covered`，正确答案是 `partly_covered`。这是最应该阻止直接进入自动审批的错误。

**汇率：Decider 把报表处理和真实付款混在一起。** 本次 ECB 来源日期为 **2026-10-12**，1 EUR = **1.1181 USD**。历史报表 EUR 10,000 应为 USD **11,181.00**；错误地用除法得到 **8,943.74** 应进入金额修正。Jev 正确区分报表、错误计算、缺失 RUB 汇率、错误日期和付款报价需求；Decider 多次选择 `obtain_executable_quote`，即使事实明确说明是历史报表、不是付款。只有题目确实要求执行付款且没有可执行报价时，这个选择才正确。

**新闻分类：两者同错一道，不能过度解读。** 从 FinancialPhraseBank 全体标注者一致的子集固定随机抽样，每类四句。双方都将“芬兰金属公司出售技术业务、推进成为最大不锈钢制造商的战略”分成中性，数据集标签为正面。这是与既有人工标签不一致，不等于已证明其投资判断必然错误，更不代表收益预测能力。

所有逐题输入、选项、参考答案和回答可在 [交互报告](report.html) 中展开，或读取 [金融结果 JSON](runs/2026-10-13-live/finance-results.json)。

## 哪些场景适合落地

| 业务用途 | 本轮证据支持的判断 |
|---|---|
| 财经新闻标签、简单工单分流 | 两者都可进入更大样本试点；本轮新闻 11/12，仍应保留人工抽查。未测试真实工单。 |
| 从清晰链接中选择目标页面 | 两者在 ECB、FDIC FAQ 均通过，可用于简单导航步骤。 |
| 搜索、填表、跨页面查找官方依据 | 本轮优先 Jev；Decider 需要先解决目标跟踪和过早结束。结束条件应由页面结果独立验证。 |
| 财报年份、金额单位、证据充分性核验 | 本轮 Jev 更可靠，可辅助分析师标注；Decider 不宜直接作为最终核验者。 |
| 存款保障额度、财务金额计算 | 两者都不宜单独承担。模型可识别账户类别、资料缺口；余额聚合、单位和汇率运算交给可审计代码。 |
| 汇率报表处理与付款需求分流 | Jev 在本轮六题通过，可以试点辅助分流；Decider 存在上下文混淆与选项顺序敏感。金额计算与付款执行仍应独立。 |

本轮测试没有使用这些落地规则替换模型答案；因此上述失败保留在分数中。独立的程序评分只判断任务结果，没有帮模型选动作。

## 来源、评分修正与限制

公开来源：

- [Microsoft Annual Report 2025](https://www.microsoft.com/investor/reports/ar25/index.html)：表格原文保存在 `preflight/microsoft.json`。
- [FDIC Understanding Deposit Insurance](https://www.fdic.gov/resources/deposit-insurance/understanding-deposit-insurance)：政策原文保存在 `preflight/fdic.json`。
- [ECB daily reference rates XML](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml)：冻结文件为 `sources/ecb-daily.xml`；保留其“仅供参考，不适合直接作为交易汇率”的说明。
- [FinancialPhraseBank](https://huggingface.co/datasets/takala/financial_phrasebank)：固定 revision `8d3fe0c36d5feec6b3cc5e455b0fcb4820fb9964`，`Sentences_AllAgree.txt`，随机种子 `20261013`。原数据许可为 [CC BY-NC-SA 3.0](sources/NEWS_LICENSE.txt)，本地保留原始许可与数据集说明。
- 浏览器访问地址和独立核验条件完整保存在 [运行前固定的计划](plan-2026-10-13.json)。

**评分器有一处修正，原始结果完整保留。** CFPB 原文为 “60 calendar days”，最初的精确子串核验误写为 “60 days”。在运行中发现后记录了 [修正说明与时间](evaluation-erratum.json)，最终用已保存页面重算这一个条件，没有重跑或修改模型动作。原始 `summary.json` 因此把 Jev 两次 CFPB 成功记为失败；本文使用 `scored-summary.json`，Jev 从 8/10 更正为 10/10，Decider 仍为 4/10。错误终点即使出现“60 days”也不能通过 URL、标题核验。

预检中，SEC investor.gov 页面返回 403；FRED 日期输入后回退，图表数据表按钮被遮挡。两项在模型测试前作为网站/工具限制排除，未计入模型失败。正式运行的 20 次任务没有浏览器动作异常或页面 JavaScript 错误；FDIC FAQ 中站外 YouTube iframe 被统一域名边界拦截，正文正常，两个模型任务均完成。

这是一组小样本诊断：全部任务和金融输入为英文；五种浏览器任务，每模型每任务两次；金融新闻为公开历史数据，无法排除训练集重叠。财报、存款和汇率题由本次作者标注，参考依据可审查，未经独立专家盲审。金融部分将已读取证据直接给模型，不能把金融分数当成“模型自主检索并决策”的端到端分数。

API 往返中位数约 Jev **139 ms**、Decider **100 ms**；P95 约 **182 ms / 304 ms**。Jev 直连 API，Decider 通过现有网关，路径不同；这些是本次部署下的请求耗时，不是纯模型推理速度。失败任务提前结束也会缩短时间，不能据此认为其完成任务更快。

## 文件与复现

所有新增文件位于当前 `validation/browser_finance/`，现有业务应用、俄罗斯方块项目和 AWS 部署未改动。

| 文件 | 用途 |
|---|---|
| `prepare.py`、`plan-2026-10-13.json` | 固定数据、任务、参考答案、预算与计划哈希 |
| `common.py` | 真实模型接入、模型身份与输出校验，无回退 |
| `browser.py` | DOM 观测、有限动作、真实浏览器执行与独立评分 |
| `runner.py` | 相同金融输入配对调用、浏览器独立重复运行 |
| `evaluate.py`、`evaluation-erratum.json` | 保留原始评分，按官方原文修正 CFPB 核验 |
| `make_report.py`、`report.html` | 无外部依赖的本地对比报告 |
| `audit.py` | 验证真实调用计数、输入配对、代码/输入/观测哈希和截图完整性 |
| `runs/2026-10-13-live/receipts.jsonl` | 178 次完整输入、原始响应、实际模型、耗时 |
| `runs/2026-10-13-live/browser/` | 20 次浏览器任务的逐步观测、截图、动作与终点 |
| `sources/manifest.json` | 公开来源文件 SHA-256 |

在当前目录执行：

```bash
uv sync --extra dev
uv run playwright install chromium
uv run pytest -q
uv run ruff check .

# 只核对现有记录，不调用模型
uv run evaluate.py --run runs/2026-10-13-live
uv run audit.py --run runs/2026-10-13-live
uv run make_report.py --run runs/2026-10-13-live --output report.html

# 再次调用真实服务：输出目录必须尚不存在，凭据只从本地文件读取
uv run runner.py \
  --plan plan-2026-10-13.json \
  --output runs/new-live-run \
  --live
uv run evaluate.py --run runs/new-live-run
```

真实重跑使用冻结金融资料与当时可访问的网站，页面更新可能影响结果。保留原计划时也保留其 CFPB 原始核验条件，因此重跑后仍需执行 `evaluate.py`。凭据路径可通过 `--credentials` 和 `--jev-key-file` 指定，服务地址可通过 `--gateway` 指定；记录文件不保存凭据或授权头。
