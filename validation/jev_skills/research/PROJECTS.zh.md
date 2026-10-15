# 项目与目录逐项研究

[综合结论](README.zh.md) · [108 场景](SCENARIOS.zh.md) · [补充应用来源](SCENARIO_SOURCES.zh.md)

编号 P01–P66 对应原页面项目表顺序；X01–X08 是其他直接项目和致谢目录。所有效果数字均为作者报告，除 P02 的公开 CSV 离线重算外，未独立复现。“未见基准”指本次读取的材料不足以支持量化结论，不声称项目任何地方都没有数据。

| 分类 | 条目数 |
| --- | ---: |
| 浏览器与桌面 | 6 |
| Agent 路由与上下文 | 7 |
| 代码质量与评测 | 7 |
| 数据检索与文档 | 5 |
| 消息分流与运营 | 6 |
| 交互界面与创作 | 6 |
| 游戏与仿真 | 5 |
| 本地模型与推理 | 13 |
| 工具与集成 | 4 |
| 研究方法与目录 | 15 |

<a id="P01"></a>

## P01 · Jev Ultrafast

**类别：** 浏览器与桌面。**业务：** 航班搜索、酒店筛选、网页资料查询。

**工作方式：** 读取索引化 DOM；Jev 选择操作和元素；Mercury 补输入文字；浏览器执行并核验。

**效果证据：** 作者航班示例 7.073 秒、17 次 Jev 加 2 次 Mercury；另有三组实现前后比较，非 Jev/Decider 对比，初始导航不计时。

**适用性判断：** 适合验证高频动作选择；必须同时统计整条任务成功率、网页等待和恢复成本。

**来源：** [项目入口](https://github.com/browser-use/jev-ultrafast) · [本次读取的版本](https://raw.githubusercontent.com/browser-use/jev-ultrafast/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/README.md)。版本 `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`。读取状态：`source_fetched`。

<a id="P02"></a>

## P02 · WebMCP / WindTunnel

**类别：** 浏览器与桌面。**业务：** 在真实网站副本上比较浏览器自动化方案。

**工作方式：** 49 个任务、8 个网站、21 种配置；比较 WebMCP 工具与 DOM/可访问性树操作。

**效果证据：** 作者 CSV 共 3,087 次尝试；本次离线重算 Jev+Mercury 的 WebMCP 为 141/147 次成功、49/49 多数通过任务；DOM 为 76/147、25/49。

**适用性判断：** 最值得借鉴的浏览器测评框架；结果说明工具表示和执行框架影响很大，不能全归功于模型。

**来源：** [项目入口](https://github.com/nekuda-ai/WindTunnel) · [本次读取的版本](https://raw.githubusercontent.com/nekuda-ai/WindTunnel/5ca8644e23826ebb30108e7bad240b61043bfe67/README.md)。版本 `5ca8644e23826ebb30108e7bad240b61043bfe67`。读取状态：`source_fetched`。

<a id="P03"></a>

## P03 · Stagehand + Jev

**类别：** 浏览器与桌面。**业务：** 把 Stagehand 网页操作与字段提取加速。

**工作方式：** 候选元素由宿主准备；Jev 选动作或原文字段；不确定时回退文本模型。

**效果证据：** 作者原帖报告 240 次真实网站测试：成功率 85%→95.4%，act 中位耗时 1.97→0.46 秒；未由我们复现。

**适用性判断：** 比较时保留相同回退条件；原文选择比让模型生成字段更易核验。

**来源：** [项目入口](https://x.com/kylejeong/status/2101046888468553855) · [本次读取的版本](https://x.com/kylejeong/status/2101046888468553855)。读取状态：`source_fetched`。

<a id="P04"></a>

## P04 · Jev Browser Use

**类别：** 浏览器与桌面。**业务：** 申请表、网站业务操作等浏览器辅助工作。

**工作方式：** Codex 负责目标、文字、视觉和最终核验，Jev 接管点击、切换、滚动等局部动作。

**效果证据：** README 报告特定项目中浏览器操作约快 5–10 倍，排除网站服务端处理；未给出同条件完整基准。

**适用性判断：** 适合混合架构示范；这不是整条业务流程提速 5–10 倍的证据。

**来源：** [项目入口](https://github.com/wy-coliney/jev-browser-use) · [本次读取的版本](https://raw.githubusercontent.com/wy-coliney/jev-browser-use/cf7e76607d4ec70592b24becadd0296dcda8177a/README.md)。版本 `cf7e76607d4ec70592b24becadd0296dcda8177a`。读取状态：`source_fetched`。

<a id="P05"></a>

## P05 · Jev Social

**类别：** 浏览器与桌面。**业务：** Instagram、TikTok、LinkedIn 内容调研。

**工作方式：** Jev 在搜索、打开、读评论等有限工具中选择；socai 操作 Chrome；可由文本模型整理带引用的报告。

**效果证据：** 有作者运行记录和示例报告，称一次报告约 64 秒；README 明确尚未发布满足重复运行条件的正式基准。

**适用性判断：** 可测证据来源覆盖率、引用正确率和报告完成率；浏览采集与报告写作分别计时。

**来源：** [项目入口](https://github.com/socai-io/jev-social) · [本次读取的版本](https://raw.githubusercontent.com/socai-io/jev-social/2776b1827e6037354e2f8b772aac689f0779bb43/README.md)。版本 `2776b1827e6037354e2f8b772aac689f0779bb43`。读取状态：`source_fetched`。

<a id="P06"></a>

## P06 · Jev Desktop

**类别：** 浏览器与桌面。**业务：** 桌面应用和浏览器中的控件操作。

**工作方式：** 利用已有 CUA 工具读取界面；并行判断操作与目标，填写值来自预先准备的本地文本槽。

**效果证据：** 有离线测试与接入示例；没有足以证明普遍提速的匹配任务数据。

**适用性判断：** 观察界面可能比决策更慢；测试应包含过期控件、失焦、空候选和重试。

**来源：** [项目入口](https://github.com/yikangy873-gif/jev-desktop) · [本次读取的版本](https://raw.githubusercontent.com/yikangy873-gif/jev-desktop/9b02783ed96a81f2529827492de708ca1956c265/README.md)。版本 `9b02783ed96a81f2529827492de708ca1956c265`。读取状态：`source_fetched`。

<a id="P07"></a>

## P07 · Jev Codex Router

**类别：** Agent 路由与上下文。**业务：** 按每轮编码任务选模型和推理档位。

**工作方式：** Jev 读取有界路由状态，输出模型与 effort；执行模型保留原会话。

**效果证据：** 237 轮历史回放的旧策略估算节省约 60%；固定原 token 用量重新计价，并非实际运行节费；当前策略已变化。

**适用性判断：** 应按实际任务质量、返工次数、端到端账单评估，不能套用旧策略节省率。

**来源：** [项目入口](https://github.com/0xNatoshi/jev-codex-router) · [本次读取的版本](https://raw.githubusercontent.com/0xNatoshi/jev-codex-router/8701ef788aa8cb0948f299538747fb01029d32b8/README.md)。版本 `8701ef788aa8cb0948f299538747fb01029d32b8`。读取状态：`source_fetched`。

<a id="P08"></a>

## P08 · Codex Jev Router (suenot)

**类别：** Agent 路由与上下文。**业务：** 从嘈杂日志中挑出编码任务需要的证据。

**工作方式：** 当前推荐路径是本地确定性证据选择 MCP；默认不用 Jev、不要求 Jev key；Laya 是可选实验。

**效果证据：** 旧 Jev 子任务路由比固定子任务便宜 27.2%，却比单个强模型贵 69.7%；当前 144 次留出测试的改善来自确定性证据选择。

**适用性判断：** 集合页描述已落后于原项目；这是先比较廉价规则基线的直接例子。

**来源：** [项目入口](https://github.com/suenot/codex-jev-router) · [本次读取的版本](https://raw.githubusercontent.com/suenot/codex-jev-router/1d4790bbd70413bca476c65070c26a1ee88888f9/README.md)。版本 `1d4790bbd70413bca476c65070c26a1ee88888f9`。读取状态：`source_fetched`。

<a id="P09"></a>

## P09 · winnow

**类别：** Agent 路由与上下文。**业务：** 减少长工具输出占用的会话空间。

**工作方式：** Jev 判断分块相关性，隐藏低相关块，保留摘要和可恢复原文的键；错误或不确定内容保留。

**效果证据：** README 指向 300 个真实样例、97 个人工盲标结果；报告 ECE、排序和隐藏后悔率；没有普遍端到端收益保证。

**适用性判断：** 关键是误删必要证据和最终任务正确率，不能仅看压缩比例；保留可逆召回。

**来源：** [项目入口](https://github.com/GhalebDweikat/winnow) · [本次读取的版本](https://raw.githubusercontent.com/GhalebDweikat/winnow/4547a81b88ac59a902bad7b0006137c7d4147aeb/README.md)。版本 `4547a81b88ac59a902bad7b0006137c7d4147aeb`。读取状态：`source_fetched`。

<a id="P10"></a>

## P10 · Jev Review

**类别：** 代码质量与评测。**业务：** 给 PR 的潜在缺陷定位、分级、排审查顺序。

**工作方式：** 逐层判断风险、文件、证据、缺陷机制及严重性，输出审查线索。

**效果证据：** 有实际决策流程与演示；尚不能据此证明缺陷发现准确率或代码安全性。

**适用性判断：** 适合辅助审查和确定阅读顺序；定位行、真实测试及独立复核仍必要。

**来源：** [项目入口](https://github.com/devagrawal09/jev-review) · [本次读取的版本](https://raw.githubusercontent.com/devagrawal09/jev-review/31f89602797fb7bea007f8a480bf368bf564954e/README.md)。版本 `31f89602797fb7bea007f8a480bf368bf564954e`。读取状态：`source_fetched`。

<a id="P11"></a>

## P11 · Blink (ellipsis-dev)

**类别：** 代码质量与评测。**业务：** 在大代码库中寻找相关文件。

**工作方式：** 多个搜索 walker 根据目录和文件名判断下一步，共享检索预算。

**效果证据：** 提供实现与测试；walker 的分配占比不是文件正确性的校准概率。

**适用性判断：** 可比较定位命中率、读取文件数和耗时；应与 rg、符号索引比较。

**来源：** [项目入口](https://github.com/ellipsis-dev/blink) · [本次读取的版本](https://raw.githubusercontent.com/ellipsis-dev/blink/a621ede75649303a933828c18c27ad800bb43ef0/README.md)。版本 `a621ede75649303a933828c18c27ad800bb43ef0`。读取状态：`source_fetched`。

<a id="P12"></a>

## P12 · fast-jev-compaction

**类别：** Agent 路由与上下文。**业务：** 裁剪编码会话里的旧工具结果。

**工作方式：** 配对工具调用与返回、固定保留最近内容，再用 Jev 判断删除或截断较早输出。

**效果证据：** 有实现，但外部分析指出给判断器的实际证据可能不足；固定删除基线能获得相近压缩，不能把缩短上下文直接记作质量收益。

**适用性判断：** 先检查请求是否包含被判内容；同题对照固定保留最近 N 轮、规则裁剪与 Jev。

**来源：** [项目入口](https://github.com/tamaratran/fast-jev-compaction) · [本次读取的版本](https://raw.githubusercontent.com/tamaratran/fast-jev-compaction/e3f262a7f4d42bd8dd32ced30d26176f7cb545b0/README.md)。版本 `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0`。读取状态：`source_fetched`。

<a id="P13"></a>

## P13 · compact-adviser

**类别：** Agent 路由与上下文。**业务：** 在合适任务边界触发上下文压缩。

**工作方式：** 判断工作类型、是否阶段结束，再由代码结合上下文压力给出提示或触发宿主操作。

**效果证据：** 作者以 40 个私人会话的 96 个检查点校准；不同宿主执行方式不同。

**适用性判断：** 应衡量压缩后续做能力、遗漏和重复读取；内部检查点标签不是公开通用基准。

**来源：** [项目入口](https://github.com/kunchenguid/compact-adviser) · [本次读取的版本](https://raw.githubusercontent.com/kunchenguid/compact-adviser/7dc0693ea7f209067453f2874d02afc2fe83b128/README.md)。版本 `7dc0693ea7f209067453f2874d02afc2fe83b128`。读取状态：`source_fetched`。

<a id="P14"></a>

## P14 · pi-warden

**类别：** Agent 路由与上下文。**业务：** 提醒编码 Agent 校验、遵守约定并避免危险步骤。

**工作方式：** Jev 语义判断与规则、事件钩子、压缩策略共同工作。

**效果证据：** 作者报告 16 天 1,168 个会话；94/124 次提醒后出现检查；另有 150 对运行的约定违规 6→0。也保留裁剪无益等负面结果。

**适用性判断：** 76% 指提醒后有检查，不是修复成功率；值得借鉴正负结果同时保留的测评方式。

**来源：** [项目入口](https://github.com/DevMortimer/pi-warden) · [本次读取的版本](https://raw.githubusercontent.com/DevMortimer/pi-warden/74989d5adf091c9cb5651450917d9f110e3fba2d/README.md)。版本 `74989d5adf091c9cb5651450917d9f110e3fba2d`。读取状态：`source_fetched`。

<a id="P15"></a>

## P15 · jev-shield (caiovicentino)

**类别：** 代码质量与评测。**业务：** 在 MCP 工具执行前筛动作风险。

**工作方式：** stdio 代理先做结构白名单，再做 Jev 语义判断和污点跟踪。

**效果证据：** 演示 10 次检查，中位 558ms、约 $0.0003；缺少足够对抗评测，非安全证明。

**适用性判断：** 可作风险提示或复核分流；硬权限由代码实施，测量误阻正常任务和漏阻两种成本。

**来源：** [项目入口](https://github.com/caiovicentino/jev-shield) · [本次读取的版本](https://raw.githubusercontent.com/caiovicentino/jev-shield/ea13a3be94c6af4ace7912de5909678e5e24941f/README.md)。版本 `ea13a3be94c6af4ace7912de5909678e5e24941f`。读取状态：`source_fetched`。

<a id="P16"></a>

## P16 · pg-jev

**类别：** 数据检索与文档。**业务：** 在 PostgreSQL 中按语义筛客服记录或文本行。

**工作方式：** 扩展提供语义谓词，数据库负责精确条件与行遍历；Jev 批量判断候选行并缓存。

**效果证据：** 作者报告 2,000 行约 3.5 秒、缓存约 50ms；批次过大出现准确率下降，环境和网络影响显著。

**适用性判断：** 适合先用 SQL 缩小候选集；比较每行准确率、批量大小、吞吐和请求总成本。

**来源：** [项目入口](https://github.com/realZachi/pg-jev) · [本次读取的版本](https://raw.githubusercontent.com/realZachi/pg-jev/e3450d44f7f6745aa2d728c9289b9ca4a6feda9a/README.md)。版本 `e3450d44f7f6745aa2d728c9289b9ca4a6feda9a`。读取状态：`source_fetched`。

<a id="P17"></a>

## P17 · jevql

**类别：** 数据检索与文档。**业务：** 不装数据库扩展也能使用语义 SQL。

**工作方式：** Go CLI/MCP/SDK 解析 SELECT，先执行普通 SQL，发送候选数据判断，再合并结果。

**效果证据：** README 给出查询契约、缓存和限制；未见可直接引用的质量基准。

**适用性判断：** 适合业务分析工具集成；应验证 SQL 支持范围、空结果及语义筛选错误。

**来源：** [项目入口](https://github.com/kylemclaren/jevql) · [本次读取的版本](https://raw.githubusercontent.com/kylemclaren/jevql/274532af852e8edfb7715ec6dca1113e589cb191/README.md)。版本 `274532af852e8edfb7715ec6dca1113e589cb191`。读取状态：`source_fetched`。

<a id="P18"></a>

## P18 · jevsearch

**类别：** 数据检索与文档。**业务：** 提升产品文档搜索的第一条命中率。

**工作方式：** 词法搜索召回前 20 条，再判断相关性、最佳条目和是否存在答案；服务异常回退词法结果。

**效果证据：** 作者 109 篇文档切成 443 块、41 个标注查询；Hit@1 41%→83%，中位延迟 8.7→278ms；候选池召回率约 83%。

**适用性判断：** 很适合与 Decider 对照；决策只能重排已有候选，不能补回未召回的答案。

**来源：** [项目入口](https://github.com/kylemclaren/jevsearch) · [本次读取的版本](https://raw.githubusercontent.com/kylemclaren/jevsearch/1df37decb960b3c4826c71b41d3393c15a8f28d3/README.md)。版本 `1df37decb960b3c4826c71b41d3393c15a8f28d3`。读取状态：`source_fetched`。

<a id="P19"></a>

## P19 · JevPDF

**类别：** 数据检索与文档。**业务：** 直接在 PDF 原文上标出问题相关证据。

**工作方式：** pdf.js 提取文本和行位置；Jev 判断每行相关性；前端高亮原文。

**效果证据：** 有可运行样例，没有完整准确率基准；非原生 OCR，扫描 PDF 需要额外转换。

**适用性判断：** 适合合同、报告审阅；重点测证据召回和无答案时是否误高亮。

**来源：** [项目入口](https://github.com/kylemclaren/jevpdf) · [本次读取的版本](https://raw.githubusercontent.com/kylemclaren/jevpdf/7f230370961c4a8e2f8b19c1729085b852124448/README.md)。版本 `7f230370961c4a8e2f8b19c1729085b852124448`。读取状态：`source_fetched`。

<a id="P20"></a>

## P20 · 1kpapers

**类别：** 数据检索与文档。**业务：** 整理年度 AI 论文和研究主题。

**工作方式：** 当前网站展示 1,018 篇论文导航和摘要成本比较。

**效果证据：** 本次访问的公开方法说明比较 DeepSeek、GPT 和 Claude 摘要成本，没有确认 Jev 在当前实现中的作用。

**适用性判断：** 保留集合页的项目线索，但不能把此站当前摘要速度或费用作为 Jev 证据。

**来源：** [项目入口](https://www.1kpapers.com/) · [本次读取的版本](https://www.1kpapers.com/)。读取状态：`source_fetched`。

<a id="P21"></a>

## P21 · 500 / 1,500-email demos

**类别：** 消息分流与运营。**业务：** 邮件分类、工作队列和标签管理。

**工作方式：** 每封邮件按需求或处理类别判断，交给收件箱规则。

**效果证据：** 聚合页转述作者约 1,500 封邮件分类；另有 500 封、3.5 美分的帖子，缺少完整标注准确率。

**适用性判断：** 吞吐演示成立与否应看原始回执；业务上线另测漏掉紧急邮件、错误归档和人工复核率。

**来源：** [项目入口](https://madewithjev.com/builds/inbox-triage-1500-emails) · [本次读取的版本](https://madewithjev.com/builds/inbox-triage-1500-emails)。读取状态：`source_fetched`。

<a id="P22"></a>

## P22 · Jev Chat Assistant

**类别：** 消息分流与运营。**业务：** 在聊天应用中理解消息并推荐回复。

**工作方式：** 读屏或 OCR 获取文字；先判断意图与风险，再生成、检查、排序候选回复；用户选择并发送。

**效果证据：** 当前原项目覆盖 Android、Windows、macOS、iOS，不再只是安卓演示；有产品说明，无统一回复质量基准。

**适用性判断：** Jev 负责判断与排序；回复文字和 OCR 由其他组件完成。可测建议采纳率与风险漏检。

**来源：** [项目入口](https://github.com/jev-chat/jev-chat-jarvis) · [本次读取的版本](https://raw.githubusercontent.com/jev-chat/jev-chat-jarvis/fdf8d28c811b0b67016d815df674cc61603c33c8/.github/README.zh-CN.md)。版本 `fdf8d28c811b0b67016d815df674cc61603c33c8`。读取状态：`source_fetched`。

<a id="P23"></a>

## P23 · 724-ad teardown

**类别：** 消息分流与运营。**业务：** 批量拆解竞品广告的 Hook、形式、Offer、CTA。

**工作方式：** 给每条广告的文本及落地页证据提出多个独立问题，汇成分析表。

**效果证据：** 作者原帖称 37 个品牌、724 条广告，40 秒、9 美分；未公开可核验的分类正确率与转化率提升。

**适用性判断：** 适合高吞吐结构化标注；不能将广告素材处理速度解释为营销 ROI。

**来源：** [项目入口](https://x.com/TheMattBerman/status/2100654891756589230) · [本次读取的版本](https://x.com/TheMattBerman/status/2100654891756589230)。读取状态：`source_fetched`。

<a id="P24"></a>

## P24 · SuperX draft scoring

**类别：** 消息分流与运营。**业务：** 为社交媒体草稿提供结构化反馈。

**工作方式：** SuperX 对每条帖子评估 61 个维度，用本地权重综合；其他模型负责生成内容。

**效果证据：** 作者称约 1 秒、$0.0004，权重参考 207 位创作者的 9,481 条帖子；预测传播表现的泛化未验证。

**适用性判断：** 可做编辑辅助；需时间切分的留出集，避免在同批历史帖子调权又报分。

**来源：** [项目入口](https://x.com/robj3d3/status/2100722975645598191) · [本次读取的版本](https://x.com/robj3d3/status/2100722975645598191)。读取状态：`source_fetched`。

<a id="P25"></a>

## P25 · Sponsor Skipper

**类别：** 消息分流与运营。**业务：** 识别长视频的赞助口播起止区间。

**工作方式：** 读带行号字幕，滑窗找段落、回溯边界，再由代码换算时间；部分模式另用转写服务。

**效果证据：** 有对 SponsorBlock 的评测入口，README 未发布可确认的总体质量分；听音模式还存在时间步长边界误差。

**适用性判断：** 可测区间 IoU、误跳正文秒数及漏掉赞助秒数，不能只测是否发现 sponsor。

**来源：** [项目入口](https://github.com/trungdq88/youtube-sponsor-detection) · [本次读取的版本](https://raw.githubusercontent.com/trungdq88/youtube-sponsor-detection/de01f0568d043035889a296a61ce21e0accc8b16/README.md)。版本 `de01f0568d043035889a296a61ce21e0accc8b16`。读取状态：`source_fetched`。

<a id="P26"></a>

## P26 · jev-ui (etweisberg)

**类别：** 交互界面与创作。**业务：** 让界面根据语义选择已写好的组件。

**工作方式：** React 的 BranchChoice、RankChoice、Gate 选择分支、排序组件和控制显示；代码负责渲染。

**效果证据：** 支持 live、replay、mock，不同模式要区分；无用户体验收益的正式测量。

**适用性判断：** 适合表单下一问、图表/表格选择；要有稳定回退和防抖，避免高频闪烁。

**来源：** [项目入口](https://github.com/etweisberg/jev-ui) · [本次读取的版本](https://raw.githubusercontent.com/etweisberg/jev-ui/42984d88e20aeb4b17af645c893c22fd71414f05/README.md)。版本 `42984d88e20aeb4b17af645c893c22fd71414f05`。读取状态：`source_fetched`。

<a id="P27"></a>

## P27 · Jevthoven

**类别：** 交互界面与创作。**业务：** 根据风格要求编排可编辑音乐。

**工作方式：** Jev 选择和弦、节奏、旋律部件，确定性音乐规则与 MIDI 编码器输出音乐。

**效果证据：** 作者当前示例为 16 小节、4 音轨、约 75–80 次决策；音乐可播放不等于听感更好。

**适用性判断：** 应测音乐规则违规、延迟与盲听偏好；不能称 Jev 直接生成音频。

**来源：** [项目入口](https://github.com/cocktailpeanut/jevthoven) · [本次读取的版本](https://raw.githubusercontent.com/cocktailpeanut/jevthoven/e5e0c67d8bae92f96c9ce05138f55c3ab72c6aac/README.md)。版本 `e5e0c67d8bae92f96c9ce05138f55c3ab72c6aac`。读取状态：`source_fetched`。

<a id="P28"></a>

## P28 · Jev Tetris

**类别：** 游戏与仿真。**业务：** 俄罗斯方块的实时落点选择。

**工作方式：** 代码枚举合法落点与棋盘特征，Jev 选择，游戏引擎执行；随机、关键词和手写启发式作对照。

**效果证据：** 三种种子下 Jev 消行 23/115/23；随机 0/0/0；启发式 118/118/116。权重曾在同三种种子调试，文档步数上限存在差异。

**适用性判断：** 能证明胜过随机，不能证明胜过专用算法；正式比较必须换留出种子并固定上限。

**来源：** [项目入口](https://github.com/thelau/jev-tetris) · [本次读取的版本](https://raw.githubusercontent.com/thelau/jev-tetris/9869b602965cf002afff766013f8c068846d36aa/README.md)。版本 `9869b602965cf002afff766013f8c068846d36aa`。读取状态：`source_fetched`。

<a id="P29"></a>

## P29 · typesafe-mario

**类别：** 游戏与仿真。**业务：** 超级马里奥的动作宏控制。

**工作方式：** 模拟器 RAM/遥测解析为角色、地形、敌人、轨迹和延迟；Jev 从 7 个动作选择，同时判断跳跃和危险程度。

**效果证据：** 开源控制框架与日志格式完整；未见可引用的通关率基准；不读取截图。

**适用性判断：** 比较到达距离、死亡数、通关率及观察至动作延迟；精确碰撞与时序计算由代码提供。

**来源：** [项目入口](https://github.com/fhshaik/typesafe-mario) · [本次读取的版本](https://raw.githubusercontent.com/fhshaik/typesafe-mario/ca22449ed187118d19326d1f54b01b6636578aa4/README.md)。版本 `ca22449ed187118d19326d1f54b01b6636578aa4`。读取状态：`source_fetched`。

<a id="P30"></a>

## P30 · Probably

**类别：** 游戏与仿真。**业务：** 在玩具编程语言中实验语义条件。

**工作方式：** Probably 把 feels、match、while 等语义判断交给 Jev，解释器执行限定分支。

**效果证据：** 作者帖子演示，缺少工程可靠性基准。

**适用性判断：** 适合教学和原型；不能用概率判断替代精确程序不变量。

**来源：** [项目入口](https://x.com/southpolesteve/status/2100767781868150938) · [本次读取的版本](https://x.com/southpolesteve/status/2100767781868150938)。读取状态：`source_fetched`。

<a id="P31"></a>

## P31 · Doom & Wikiracing

**类别：** 游戏与仿真。**业务：** Doom 实时控制和 Wikipedia 链接寻路。

**工作方式：** 结构化游戏状态映射为动作；Wikiracing 从当前页实际链接中选择下一页。

**效果证据：** 官方演示说明 Doom 使用结构化文本而非截图，并承认传统游戏 bot 可更强；演示耗时非通用任务保证。

**适用性判断：** 同时测目标达成、动作次数和延迟；高频决策优势必须与整个循环吞吐区分。

**来源：** [项目入口](https://typesafe.ai/blog/introducing-system-one-models-and-jev) · [本次读取的版本](https://typesafe.ai/blog/introducing-system-one-models-and-jev)。读取状态：`source_fetched`。

<a id="P32"></a>

## P32 · OpenJev (DiffusionGemma)

**类别：** 本地模型与推理。**业务：** 自部署兼容 typed-decision 接口的推理服务。

**工作方式：** OpenJev 使用 DiffusionGemma 等独立模型与 GPU/MLX 后端，另支持不同模型路线。

**效果证据：** 有硬件和并发记录，存在大并发超时；不是官方 Jev 权重，也没有证明训练与能力等同。

**适用性判断：** 是独立推理方案，可纳入同题对照；需单列设备、模型、上下文和吞吐限制。

**来源：** [项目入口](https://github.com/razorback16/openjev) · [本次读取的版本](https://raw.githubusercontent.com/razorback16/openjev/dba783d9ce5327c1f97932a3074fd0c5bf5cb0d1/README.md)。版本 `dba783d9ce5327c1f97932a3074fd0c5bf5cb0d1`。读取状态：`source_fetched`。

<a id="P33"></a>

## P33 · OpenJev SGLang

**类别：** 本地模型与推理。**业务：** 用 SGLang 的共享前缀和 logprob 做封闭判断。

**工作方式：** 早期 OpenJev-SGLang 示例基于 Qwen；当前 README 建议使用 SGLang 原生 decisions API。

**效果证据：** 有 B200 上的推理实验；早期 N 个问题涉及 N+1 次调用，不应宣传为官方 Jev 的单前向复现。

**适用性判断：** 对照时记录实际请求数与缓存状态；输出熵不是已验证的业务校准。

**来源：** [项目入口](https://github.com/ekzhang/openjev-sglang) · [本次读取的版本](https://raw.githubusercontent.com/ekzhang/openjev-sglang/bf6a53bbb1f75040b06de39abff1230524553ab5/README.md)。版本 `bf6a53bbb1f75040b06de39abff1230524553ab5`。读取状态：`source_fetched`。

<a id="P34"></a>

## P34 · Jevify

**类别：** 本地模型与推理。**业务：** 把现有 LLM 服务适配成 typed-decision 接口。

**工作方式：** jevify 使用本地或远端 logprob 后端，提供配方、探测和评分卡。

**效果证据：** 主要是适配层，没有独立训练权重；简单题高分不能代表困难任务表现。

**适用性判断：** 适合统一接口做公平比较；协议兼容与判断正确率分别验收。

**来源：** [项目入口](https://github.com/fidecastro/jevify) · [本次读取的版本](https://raw.githubusercontent.com/fidecastro/jevify/2eace0905a883f6eff9bb5796a67b3be895eafa0/README.md)。版本 `2eace0905a883f6eff9bb5796a67b3be895eafa0`。读取状态：`source_fetched`。

<a id="P35"></a>

## P35 · jevlike

**类别：** 本地模型与推理。**业务：** 研究小型动态选项决策模型的训练。

**工作方式：** jevlike 使用字节或冻结编码器特征，训练候选打分头，并提供游戏实验。

**效果证据：** 作者游戏结果包含负奖励和输给 Stockfish 的结果；精选视频片段不足以证明强游戏能力。

**适用性判断：** 适合研究训练与动作表示；优先看完整种子结果而非演示片段。

**来源：** [项目入口](https://github.com/vinnylarouge/jevlike) · [本次读取的版本](https://raw.githubusercontent.com/vinnylarouge/jevlike/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/README.md)。版本 `94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452`。读取状态：`source_fetched`。

<a id="P36"></a>

## P36 · Jev on a laptop

**类别：** 本地模型与推理。**业务：** 在笔记本上快速输出多字段选择。

**工作方式：** 原始小型 Qwen 加 MLX，共享状态 KV，再对有界字段并行评分。

**效果证据：** 作者示例 1.5B、28 字段约 0.4 秒；格式完整不是 28 个字段都正确。

**适用性判断：** 适合本地低延迟实验；必须增加逐字段语义标注。

**来源：** [项目入口](https://github.com/rorshopping/jev-on-a-laptop) · [本次读取的版本](https://raw.githubusercontent.com/rorshopping/jev-on-a-laptop/5821d910610331a695f5185a6ad1d6b514e8a62f/README.md)。版本 `5821d910610331a695f5185a6ad1d6b514e8a62f`。读取状态：`source_fetched`。

<a id="P37"></a>

## P37 · Qwen-2.5-1B-RLCD

**类别：** 本地模型与推理。**业务：** 在 Apple 芯片上运行 Qwen 决策推理代码。

**工作方式：** HF 名称带 RLCD，实际公开内容是 Qwen2.5-1.5B 的推理代码与预设。

**效果证据：** 本次核对 HF 文件列表没有模型权重；未见 RLCD 训练产物，作者仅报告特定配置加速。

**适用性判断：** 不能列作已发布的新训练模型；先区分算法代码、适配器与权重。

**来源：** [项目入口](https://huggingface.co/harshatheg/Qwen-2.5-1B-RLCD) · [本次读取的版本](https://huggingface.co/harshatheg/Qwen-2.5-1B-RLCD/raw/2af86848be75847ccb3553b0941cc51d6ef7e4e9/README.md)。版本 `2af86848be75847ccb3553b0941cc51d6ef7e4e9`。读取状态：`source_fetched`。

<a id="P38"></a>

## P38 · SemIf

**类别：** 本地模型与推理。**业务：** 用现有开源模型直接读取候选概率。

**工作方式：** SemIf 支持 Torch、MLX、MPS、llama.cpp 等，比较二选一判定与 JSON 生成。

**效果证据：** 作者 21 题约 1.023 秒对 5.332 秒，但答案只一致 18/21；加速并不保持完全相同语义输出。

**适用性判断：** 比较吞吐时也应比较标签正确率、缓存引起的变化和硬件。

**来源：** [项目入口](https://github.com/TheoLeeCJ/SemIf) · [本次读取的版本](https://raw.githubusercontent.com/TheoLeeCJ/SemIf/23cf1f39fc9534fe81437200959b6dfc7106e45a/README.md)。版本 `23cf1f39fc9534fe81437200959b6dfc7106e45a`。读取状态：`source_fetched`。

<a id="P39"></a>

## P39 · LitJev

**类别：** 本地模型与推理。**业务：** 验证一种 Jev 类候选打分服务实现。

**工作方式：** LitJev 对候选文本做 logprob 打分并归一化；服务接口保持相似。

**效果证据：** 属于独立实现假设，不是官方内部架构确认；默认概率未经任务校准，存在批处理配置限制。

**适用性判断：** 适合架构实验；不要把 softmax 直接解释为正确概率。

**来源：** [项目入口](https://github.com/zhengxuyu/litjev) · [本次读取的版本](https://raw.githubusercontent.com/zhengxuyu/litjev/2cd915aff989b37bb1c46ef5ae480c4a01501404/README.md)。版本 `2cd915aff989b37bb1c46ef5ae480c4a01501404`。读取状态：`source_fetched`。

<a id="P40"></a>

## P40 · Laya

**类别：** 本地模型与推理。**业务：** 本地、低延迟、多语言分类和有序评分。

**工作方式：** Laya 为独立编码器决策模型，HF 有基础、多语言和 typed-decision 权重。

**效果证据：** 作者报告 2,000 道 typed-decision 题从基础模型 0.362 提升到微调 0.766；长输入延迟和截断设置差异大。

**适用性判断：** 更像真正本地部署候选；按当前权重版本、语言和上下文长度分别评估。

**来源：** [项目入口](https://huggingface.co/convaiinnovations/laya) · [本次读取的版本](https://huggingface.co/convaiinnovations/laya/raw/7b928d828b7b0e022f929d9bd2e44165aa270148/README.md)。版本 `7b928d828b7b0e022f929d9bd2e44165aa270148`。读取状态：`source_fetched`。

<a id="P41"></a>

## P41 · LFM2.5-350M-RLCD

**类别：** 本地模型与推理。**业务：** 让 350M 小模型批量填闭集字段。

**工作方式：** 基于未重训的 LFM2.5-350M 做受约束推理，提供原始权重。

**效果证据：** 作者 28 字段样例加速明显，但字段准确率约 60.7%/64.3%；255 选项反而更慢。

**适用性判断：** 名称含 RLCD 不代表经过该方法训练；必须同时报告规模变化、速度与质量。

**来源：** [项目入口](https://huggingface.co/notnotsamuel/LFM2.5-350M-RLCD) · [本次读取的版本](https://huggingface.co/notnotsamuel/LFM2.5-350M-RLCD/raw/deb589d803d141cabd158ef55f6617b128529f36/README.md)。版本 `deb589d803d141cabd158ef55f6617b128529f36`。读取状态：`source_fetched`。

<a id="P42"></a>

## P42 · LFM2.5-2.6B-RLCD

**类别：** 本地模型与推理。**业务：** 研究 2.6B 模型的并行字段读取。

**工作方式：** 未改变原始 LFM 权重，使用实验性的推理方法。

**效果证据：** 作者新鲜审计数据并行方式 72.2%，自回归 94.4%，准确率门槛未通过；置信度未校准。

**适用性判断：** 这是重要负例：更快并不自动适合作业务判断。

**来源：** [项目入口](https://huggingface.co/monotykamary/LFM2.5-2.6B-RLCD) · [本次读取的版本](https://huggingface.co/monotykamary/LFM2.5-2.6B-RLCD/raw/31455458983bdbdc41b69ebbcedabd0d5de299c9/README.md)。版本 `31455458983bdbdc41b69ebbcedabd0d5de299c9`。读取状态：`source_fetched`。

<a id="P43"></a>

## P43 · Verdict / rlcd-modernbert-151m

**类别：** 本地模型与推理。**业务：** 在小型编码器上研究校准与决策训练。

**工作方式：** Verdict 基于 ModernBERT/GLiClass，独立训练并做概率校准。

**效果证据：** 公开题集有校准改善，但困难 111 题准确率约 36.9%未变；上下文较短。

**适用性判断：** 校准能帮助分流错误，不能创造不存在的识别能力。

**来源：** [项目入口](https://github.com/Heman10x-NGU/Verdict-open-jev) · [本次读取的版本](https://raw.githubusercontent.com/Heman10x-NGU/Verdict-open-jev/30f15564821626ca5c1ad5b2638c4eb7078787dd/README.md)。版本 `30f15564821626ca5c1ad5b2638c4eb7078787dd`。读取状态：`source_fetched`。

<a id="P44"></a>

## P44 · jevos

**类别：** 本地模型与推理。**业务：** 在 CPU 上提供低延迟决策 API。

**工作方式：** jevos 当前 v4 支持 noul、choice 及早期 score，含 OpenVINO/int8、GGUF 路线。

**效果证据：** 作者短状态中位约 28ms、长状态约 130ms；多组质量分低于 Jev，六组中五组参与过选 checkpoint。

**适用性判断：** 集合页仅支持 noul 的描述过时；本地速度不能直接作为同质量加速比。

**来源：** [项目入口](https://github.com/feder-cr/jev) · [本次读取的版本](https://raw.githubusercontent.com/feder-cr/jev/a8c2eff26c964724013b409e0e2def002111671d/README.md)。版本 `a8c2eff26c964724013b409e0e2def002111671d`。读取状态：`source_fetched`。

<a id="P45"></a>

## P45 · TypeSafe MCP

**类别：** 工具与集成。**业务：** 给现有 Agent 接上多个决策模型。

**工作方式：** 原 typesafe-mcp 已发展为 System One Connector；通过 MCP/CLI 输出可分支的 noul、choice、score，支持模型 profile。

**效果证据：** 有多模型和批量接口文档，属于接入工具，不是准确率基准。

**适用性判断：** 适合复用接口设计；接上模型不代表每种宿主都完成业务验证。

**来源：** [项目入口](https://github.com/itsmostafa/typesafe-mcp) · [本次读取的版本](https://raw.githubusercontent.com/itsmostafa/typesafe-mcp/87ee58a62be235e8d5ec02a448c3c8c64e5562dd/README.md)。版本 `87ee58a62be235e8d5ec02a448c3c8c64e5562dd`。读取状态：`source_fetched`。

<a id="P46"></a>

## P46 · Jev MCP (jkudish)

**类别：** 工具与集成。**业务：** 通过 MCP 完成核验、分类、检索、抽取和审查。

**工作方式：** 12 个工具拆成明确判断问题；原文抽取先找候选；无答案检查与选择分开，代码验证响应。

**效果证据：** 有真实 I/O 示例与完整错误分支；部分评分来自其他 cookbook 或私人实验。

**适用性判断：** 最值得借鉴的是无答案路径、对象一致性检查和无效响应处理；默认阈值仍需业务校准。

**来源：** [项目入口](https://github.com/jkudish/jev-mcp) · [本次读取的版本](https://raw.githubusercontent.com/jkudish/jev-mcp/86eae7861c60ea99a1b2eab2881db0fb1164fcc0/README.md)。版本 `86eae7861c60ea99a1b2eab2881db0fb1164fcc0`。读取状态：`source_fetched`。

<a id="P47"></a>

## P47 · SemDecide

**类别：** 工具与集成。**业务：** 在 Unix 管道和 CI 中增加语义过滤。

**工作方式：** SemDecide 提供 is、choose、score、filter、guard，并用不同退出码区分假、不确定和服务失败。

**效果证据：** README 给出可执行契约与测试方式，无通用业务准确率数据。

**适用性判断：** 很适合接现有流水线；退出码要把模型拒绝判断和 API 失败分开。

**来源：** [项目入口](https://github.com/sharziki/semdecide) · [本次读取的版本](https://raw.githubusercontent.com/sharziki/semdecide/33cf5c03c50e02e59df3f3ea81f0650f6b791545/README.md)。版本 `33cf5c03c50e02e59df3f3ea81f0650f6b791545`。读取状态：`source_fetched`。

<a id="P48"></a>

## P48 · Supercov

**类别：** 代码质量与评测。**业务：** 指导编码 Agent 找测试缺口与代码风险。

**工作方式：** Supercov 真实执行测试取得覆盖率；Jev 负责代码味道、安全线索及断言可能覆盖情况。

**效果证据：** 提供覆盖率记录、差异和多语言集成；模型对断言覆盖的预测不等于真实变异测试。

**适用性判断：** 可借鉴测试证据与语义提示并排展示；最终改善要靠真实测试和缺陷验证。

**来源：** [项目入口](https://github.com/supercorp-ai/supercov) · [本次读取的版本](https://raw.githubusercontent.com/supercorp-ai/supercov/ebf637118fae3d6c218d730835d1088efe59460e/README.md)。版本 `ebf637118fae3d6c218d730835d1088efe59460e`。读取状态：`source_fetched`。

<a id="P49"></a>

## P49 · jev-skill-gate

**类别：** Agent 路由与上下文。**业务：** 从大量 skills 中选择需要加载的描述。

**工作方式：** 按任务判断相关性，写入完整描述、仅名称或隐藏三种可见状态；保留本地 TF-IDF 基线。

**效果证据：** 217 个 skills，Jev 完成 4/20 个样例，19 个预期技能均保留但其中 5 个仅名称；阈值曾据这些案例调整。

**适用性判断：** 75%为特定示例的描述 token 估算节省；应另用留出任务测召回和实际任务质量。

**来源：** [项目入口](https://github.com/ShivamPansuriya/jev-skill-gate) · [本次读取的版本](https://raw.githubusercontent.com/ShivamPansuriya/jev-skill-gate/6468fa596be757e7f700dd8bb3bd88ddc66ad397/README.md)。版本 `6468fa596be757e7f700dd8bb3bd88ddc66ad397`。读取状态：`source_fetched`。

<a id="P50"></a>

## P50 · Jev + Kimi fraud experiment

**类别：** 消息分流与运营。**业务：** Jev 快速筛选、Kimi 深度处理的反欺诈线索。

**工作方式：** 集合页将其列为串联决策与强模型的应用，但链接只到 Made with Jev 首页。

**效果证据：** 当前页面未定位到这一项目的独立实现、数据集或结果；与 P60 为同一入口。

**适用性判断：** 可以作为架构设想；不能给出已验证的欺诈识别效果。

**来源：** [项目入口](https://madewithjev.com/) · [本次读取的版本](https://madewithjev.com/)。读取状态：`source_fetched`。

<a id="P51"></a>

## P51 · TypeSafe AI Playground

**类别：** 交互界面与创作。**业务：** 在可视化工作台学习并检查决策流程。

**工作方式：** 社区 Playground 覆盖语言、Agent、代码治理、仿真及街机五组；包含浏览器、提取、Z3、Doom、象棋、魔方、贪吃蛇、打砖块等。

**效果证据：** 明确区分 Live Jev、mock、真实本地求解器和模拟工具；有些浏览器线上目标仍受 key/余额问题阻塞。

**适用性判断：** 它不是所有项目均成功的排行榜；重点借鉴可见证据、同种子基线和独立结果核验。

**来源：** [项目入口](https://github.com/TypeSafeAI/typesafe-playground) · [本次读取的版本](https://raw.githubusercontent.com/TypeSafeAI/typesafe-playground/f524842a88fa4df323d3a65b48e49fb43df92e53/README.md)。版本 `f524842a88fa4df323d3a65b48e49fb43df92e53`。读取状态：`source_fetched`。

<a id="P52"></a>

## P52 · Jev Explained

**类别：** 交互界面与创作。**业务：** 向开发者解释三种决策输出。

**工作方式：** 交互式输入与可视化展示 noul、choice、score 及返回值。

**效果证据：** 教学演示，不是生产系统效果评估。

**适用性判断：** 适合团队培训与检查问题写法，不应统计成实际业务成功率。

**来源：** [项目入口](https://github.com/davila7/jev-explained) · [本次读取的版本](https://raw.githubusercontent.com/davila7/jev-explained/5cbe35e04609112be77b1bd447bd79b3bde7980b/README.md)。版本 `5cbe35e04609112be77b1bd447bd79b3bde7980b`。读取状态：`source_fetched`。

<a id="P53"></a>

## P53 · jev-evaluation

**类别：** 代码质量与评测。**业务：** 系统研究 Jev 的能力、校准、批量与抗干扰边界。

**工作方式：** 预先固定九组实验及可证伪预测，使用构造或求解器真值，记录请求与失败。

**效果证据：** 作者 123,805 请求；支持工单路由校准较好，但随机 3-SAT 表现差；60 工单用可识别主体提问比仅序号可靠得多；伪装权威的注入可明显改变结果。

**适用性判断：** 选业务时需检查真值、对象绑定、分布外输入和阈值；类型正确不保证语义正确。

**来源：** [项目入口](https://github.com/willkelly/jev-evaluation) · [本次读取的版本](https://raw.githubusercontent.com/willkelly/jev-evaluation/d80f375621ad4b9306c6dff6941242925d7e2386/README.md)。版本 `d80f375621ad4b9306c6dff6941242925d7e2386`。读取状态：`source_fetched`。

<a id="P54"></a>

## P54 · PrimeLine comparison

**类别：** 代码质量与评测。**业务：** 比较实际提交信息分类、知识库分类和置信度分流。

**工作方式：** 预注册与修订后数据、多个模型，比较全量准确率和保留一定覆盖率后的准确率。

**效果证据：** 四模型表：800 条提交 Jev 65.8%，Haiku 54.6%；450 条知识库 Jev 90.7%，Haiku 97.8%；作者纠正过不公平的筛选集合比较。

**适用性判断：** 低置信度转交有价值但不能跨任务套阈值；同覆盖率不等于同一批样本，需同时报告。

**来源：** [项目入口](https://primeline.cc/blog/typesafe-jev-pre-registered-test) · [本次读取的版本](https://primeline.cc/blog/typesafe-jev-pre-registered-test)。读取状态：`source_fetched`。

<a id="P55"></a>

## P55 · LangChain Jev-as-a-Judge

**类别：** 代码质量与评测。**业务：** 把决策模型作为 Agent 输出质量裁判。

**工作方式：** 固定五个天气 Agent 轨迹，每个重复 100 次，与人工标签比较通过与质量评分。

**效果证据：** 作者 Jev 500/500 二元判断一致，质量方差低、平均约 0.44 秒；只有五种独立案例，模型服务版本未记录。

**适用性判断：** 证明窄样本重复稳定，不证明 500 种任务全对；稳定性与准确率分开测。

**来源：** [项目入口](https://www.langchain.com/blog/jev-agent-evals-langsmith) · [本次读取的版本](https://www.langchain.com/blog/jev-agent-evals-langsmith)。读取状态：`source_fetched`。

<a id="P56"></a>

## P56 · Jev in the Wild: A Data-Driven Analysis of the Jev Model's Functionality, Applications and Ecosystem

**类别：** 研究方法与目录。**业务：** 观察开发者如何采用 System One 模型。

**工作方式：** 论文分析 2,170 个 GitHub 项目，归纳采用方式和架构趋势。

**效果证据：** 生态观察研究，非 Jev 或 Decider 的质量对照实验。

**适用性判断：** 帮助找业务方向与模式；项目数量、关注度不能当作技术有效性证据。

**来源：** [项目入口](https://arxiv.org/abs/2609.30216) · [本次读取的版本](https://arxiv.org/abs/2609.30216)。读取状态：`source_fetched`。

<a id="P57"></a>

## P57 · HarmBench

**类别：** 研究方法与目录。**业务：** 标准化模型防护和拒答的评测。

**工作方式：** HarmBench 提供数据、攻击方法、目标模型与判分流程。

**效果证据：** 是通用安全评测框架，未由该链接证明 Jev 已接入或表现如何。

**适用性判断：** 可借鉴固定真值、攻击成功率及正常任务对照；归类为方法参考。

**来源：** [项目入口](https://github.com/centerforaisafety/HarmBench) · [本次读取的版本](https://raw.githubusercontent.com/centerforaisafety/HarmBench/8e1604d1171fe8a48d8febecd22f600e462bdcdd/README.md)。版本 `8e1604d1171fe8a48d8febecd22f600e462bdcdd`。读取状态：`source_fetched`。

<a id="P58"></a>

## P58 · PAIR

**类别：** 研究方法与目录。**业务：** 研究黑盒模型的多轮对抗评测。

**工作方式：** PAIR 使用独立攻击模型、目标模型和裁判迭代评测。

**效果证据：** 原研究与 Jev 无直接实测关系；不是 Jev 应用产品。

**适用性判断：** 仅作评测方法参考，不应列入 Jev 业务收益统计。

**来源：** [项目入口](https://github.com/patrickrchao/JailbreakingLLMs) · [本次读取的版本](https://raw.githubusercontent.com/patrickrchao/JailbreakingLLMs/6379ef705a0fc745530f7d895963510c021b496a/README.md)。版本 `6379ef705a0fc745530f7d895963510c021b496a`。读取状态：`source_fetched`。

<a id="P59"></a>

## P59 · AgentDojo

**类别：** 研究方法与目录。**业务：** 在有真实工具环境的任务中测提示注入防御。

**工作方式：** AgentDojo 同时记录正常任务效用与受攻击结果。

**效果证据：** 通用动态基准，不是现成 Jev 成绩。

**适用性判断：** 比单句注入标签更接近 Agent 实际执行，可用于未来隔离评测。

**来源：** [项目入口](https://github.com/ethz-spylab/agentdojo) · [本次读取的版本](https://raw.githubusercontent.com/ethz-spylab/agentdojo/089ed468cf3ed0322acc66b0211f26d9d90dbf60/README.md)。版本 `089ed468cf3ed0322acc66b0211f26d9d90dbf60`。读取状态：`source_fetched`。

<a id="P60"></a>

## P60 · Made with Jev

**类别：** 研究方法与目录。**业务：** 查找 Jev 社区应用、案例和演示。

**工作方式：** Made with Jev 按行业和项目类型聚合外部材料。

**效果证据：** 抓取时首页列 838 个 builds，分类重叠；数据随时间变化、均需回原始来源验证。

**适用性判断：** 是发现入口，不是 838 个都已验证的应用；与 P50 URL 重复。

**来源：** [项目入口](https://madewithjev.com/) · [本次读取的版本](https://madewithjev.com/)。读取状态：`source_fetched`。

<a id="P61"></a>

## P61 · Awesome Jev (kraayenjon)

**类别：** 研究方法与目录。**业务：** 按业务找 Jev 项目与实现模式。

**工作方式：** awesome-jev 整理应用、SDK、游戏、模式和评测，并关联 Made with Jev。

**效果证据：** 目录 README 可读，含大量外链；目录收录本身不构成测试。

**适用性判断：** 用于继续选题，本文不声称递归验证所有目录子链接。

**来源：** [项目入口](https://github.com/kraayenjon/awesome-jev) · [本次读取的版本](https://raw.githubusercontent.com/kraayenjon/awesome-jev/ea358b03743c8c7a26ff4467fc8fc99516a67c46/README.md)。版本 `ea358b03743c8c7a26ff4467fc8fc99516a67c46`。读取状态：`source_fetched`。

<a id="P62"></a>

## P62 · Awesome Jev (Anil-matcha)

**类别：** 研究方法与目录。**业务：** 社区 awesome 清单入口。

**工作方式：** 仓库存在，但当前根 README 是空文件。

**效果证据：** 成功读取到空 README，无法根据原项目文档核实集合页描述。

**适用性判断：** 记录为空来源，不能用目录名称补造项目详情。

**来源：** [项目入口](https://github.com/Anil-matcha/awesome-jev-by-typesafe) · [本次读取的版本](https://github.com/Anil-matcha/awesome-jev-by-typesafe)。版本 `74c766198ff5c75feecadaeef0829808b9039288`。读取状态：`empty_readme`。

<a id="P63"></a>

## P63 · LINUX DO / QianCheng

**类别：** 研究方法与目录。**业务：** 中文社区应用演示汇总。

**工作方式：** linux.do 讨论串作为社区发现入口。

**效果证据：** 本次访问返回 HTTP 403；页面内其他直接原帖链接已另行追踪。

**适用性判断：** 明确保留未能读取状态，不将其写成已完整核实。

**来源：** [项目入口](https://linux.do/t/topic/2919004) · [本次读取的版本](https://linux.do/t/topic/2919004)。读取状态：`source_unavailable`。

<a id="P64"></a>

## P64 · laya.tools

**类别：** 研究方法与目录。**业务：** 查找本地 Laya 的工具、运行时和游戏。

**工作方式：** laya.tools 聚合仓库、HF 模型、演示与托管服务。

**效果证据：** 抓取时列 1,944 个项目，首页有本地决策示例；社区速度声称不等于独立质量比较。

**适用性判断：** 本地生态选型入口；实际部署候选应回权重卡和仓库核对。

**来源：** [项目入口](https://laya.tools) · [本次读取的版本](https://laya.tools)。读取状态：`source_fetched`。

<a id="P65"></a>

## P65 · Awesome Jev (OmniJev)

**类别：** 研究方法与目录。**业务：** 整理 System One 论文、模型和评测。

**工作方式：** OmniJev gallery 汇总研究背景、开源模型、应用与基准。

**效果证据：** 有结构化研究清单和来源，属于二级资料。

**适用性判断：** 帮助区分原模型、推理适配与独立训练，不能把收录当能力认证。

**来源：** [项目入口](https://github.com/OmniJev/awesome-jev-gallery) · [本次读取的版本](https://raw.githubusercontent.com/OmniJev/awesome-jev-gallery/15a61c0209d699bc9350d5585ff767d0c1077e2d/README.md)。版本 `15a61c0209d699bc9350d5585ff767d0c1077e2d`。读取状态：`source_fetched`。

<a id="P66"></a>

## P66 · prompt2jev

**类别：** 工具与集成。**业务：** 把已有分类 prompt 改为可执行决策调用。

**工作方式：** prompt2jev 读取需求、prompt 或调用代码，拆原子问题，把算术与精确规则放代码，生成请求与脚本。

**效果证据：** 有五类模板、离线校验及端到端示例；生成脚本可运行不等于业务判断正确。

**适用性判断：** 适合迁移现有标签/分数/布尔输出调用；需为转换前后保留同题质量对照。

**来源：** [项目入口](https://github.com/sumleo/prompt2jev) · [本次读取的版本](https://raw.githubusercontent.com/sumleo/prompt2jev/f3b6bc763b742b9f489bf0fa0c9514e334996283/README.md)。版本 `f3b6bc763b742b9f489bf0fa0c9514e334996283`。读取状态：`source_fetched`。

<a id="X01"></a>

## X01 · Whale city

**类别：** 交互界面与创作。**业务：** 鲸背城市的交互叙事和视频呈现。

**工作方式：** 大模型设计世界，Jev 从动作中选择，视频模型将选定场景渲染为短片。

**效果证据：** 作者原帖称 264 段视频与决策共约 5 分钟；缺少公开代码和决策质量评测。

**适用性判断：** 展示三种能力分工；不能把整套视频生成速度归为 Jev 推理速度。

**来源：** [项目入口](https://x.com/gokayfem/status/2101022590722810271) · [本次读取的版本](https://x.com/gokayfem/status/2101022590722810271)。读取状态：`source_fetched`。

<a id="X02"></a>

## X02 · jev-trader

**类别：** 游戏与仿真。**业务：** 用订单簿回放研究高频交易决策。

**工作方式：** Jev 根据市场状态选买卖，代码负责仓位限制、过期处理、挂单与成交记账。

**效果证据：** 默认 mock+dry-run，部署示例也为模拟；README 的循环 p50 100ms 含 mock 80ms，非真实 Jev 实盘收益。

**适用性判断：** 只可据此研究决策/执行/成交差别；无盈利证据，不能把发单意图算成交。

**来源：** [项目入口](https://github.com/jarrodwatts/jev-trader) · [本次读取的版本](https://raw.githubusercontent.com/jarrodwatts/jev-trader/b587759e459ea049590102e54a0b07800864cdc3/README.md)。版本 `b587759e459ea049590102e54a0b07800864cdc3`。读取状态：`source_fetched`。

<a id="X03"></a>

## X03 · ST-jeved

**类别：** 交互界面与创作。**业务：** 持续检查角色扮演的节奏、人设与规则。

**工作方式：** ST-jeved 在回复前后读取聊天，传感器给分/分类；规则添加提示、重抽、更新剧情列表或调用脚本。

**效果证据：** 有完整插件契约与超时、冷却、撤销设计；没有故事质量的对照结果。

**适用性判断：** 适合长期互动状态监测；内容仍由聊天模型生成，测偏离率与误触发。

**来源：** [项目入口](https://github.com/mossyfield/ST-jeved) · [本次读取的版本](https://raw.githubusercontent.com/mossyfield/ST-jeved/fec4a2d7edc3471d6860d438a7e4133b55d47c2d/README.md)。版本 `fec4a2d7edc3471d6860d438a7e4133b55d47c2d`。读取状态：`source_fetched`。

<a id="X04"></a>

## X04 · cobanov/awesome-jev

**类别：** 研究方法与目录。**业务：** 发现按能力分类的 Jev 应用。

**工作方式：** cobanov 清单覆盖集成、浏览器、上下文、游戏、媒体、开放模型和评测。

**效果证据：** 已核对目录结构和来源属性；不是独立评测集。

**适用性判断：** 作为原页面致谢来源追踪，子链接不重复算作本次独立研究项目。

**来源：** [项目入口](https://github.com/cobanov/awesome-jev) · [本次读取的版本](https://raw.githubusercontent.com/cobanov/awesome-jev/fd1dae00a49ce8b8bbe8b02e2f909f26c2243838/README.md)。版本 `fd1dae00a49ce8b8bbe8b02e2f909f26c2243838`。读取状态：`source_fetched`。

<a id="X05"></a>

## X05 · yibie/awesome-jev

**类别：** 研究方法与目录。**业务：** 按任务和编码宿主找社区实践。

**工作方式：** yibie 清单由分类文件生成聚合 README，包含应用、集成与采用方式。

**效果证据：** 明确收录不等于背书；有大量外链而非同条件测试数据。

**适用性判断：** 适合继续检索，需去具体项目核验状态和结果。

**来源：** [项目入口](https://github.com/yibie/awesome-jev) · [本次读取的版本](https://raw.githubusercontent.com/yibie/awesome-jev/7afe0e1680cecee1e5942b7ed6949c9283eaec53/README.md)。版本 `7afe0e1680cecee1e5942b7ed6949c9283eaec53`。读取状态：`source_fetched`。

<a id="X06"></a>

## X06 · yzfly/awesome-jev-zh

**类别：** 研究方法与目录。**业务：** 中文学习与应用入口。

**工作方式：** yzfly 清单含应用、演示、SDK、复现、中文指南和自动热门榜。

**效果证据：** 讲解与自动收录并存，排名和速度介绍不等于能力验证。

**适用性判断：** 作为中文索引；注意热门列表动态更新和二手数字。

**来源：** [项目入口](https://github.com/yzfly/awesome-jev-zh) · [本次读取的版本](https://raw.githubusercontent.com/yzfly/awesome-jev-zh/d93ebcbc7f08c34c0c017e91eab80144cddde3ed/README.md)。版本 `d93ebcbc7f08c34c0c017e91eab80144cddde3ed`。读取状态：`source_fetched`。

<a id="X07"></a>

## X07 · hellogumbo/awesome-jev

**类别：** 研究方法与目录。**业务：** 搜索 Jev 项目生态。

**工作方式：** hellogumbo 清单对应 awesomejev.com，覆盖应用、游戏、集成和研究。

**效果证据：** 目录条目及星数会更新，无统一质量门槛。

**适用性判断：** 用于发现相关仓库，保留原始来源核验步骤。

**来源：** [项目入口](https://github.com/hellogumbo/awesome-jev) · [本次读取的版本](https://raw.githubusercontent.com/hellogumbo/awesome-jev/4e0d0a9f3c09b0b81f89b654a287488f8feea1e5/README.md)。版本 `4e0d0a9f3c09b0b81f89b654a287488f8feea1e5`。读取状态：`source_fetched`。

<a id="X08"></a>

## X08 · logicrw/awesome-jev-projects

**类别：** 研究方法与目录。**业务：** 按系统架构环节查找项目。

**工作方式：** logicrw radar 分类包括 Browser、Context GC、Model Routing、CLI、Voice 等，并含赞助位。

**效果证据：** 项目目录与架构分类，不是所有收录项目的独立效果报告。

**适用性判断：** 适合梳理组件组合；付费展示、数量与技术结果分别看待。

**来源：** [项目入口](https://github.com/logicrw/awesome-jev-projects) · [本次读取的版本](https://raw.githubusercontent.com/logicrw/awesome-jev-projects/a7119a88aed5d3b3251b118e73478d2532f1258a/README.md)。版本 `a7119a88aed5d3b3251b118e73478d2532f1258a`。读取状态：`source_fetched`。
