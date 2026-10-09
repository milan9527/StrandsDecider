let ui,
  catalog,
  current = "pending",
  loaded = false,
  loading = false;
let busy = false,
  stopRequested = false,
  mode = "live",
  selectedStage = "intake";
const workspaces = new Map();
const providers = ["decider", "bedrock"];
const providerNames = { decider: "Strands Decider", bedrock: "GPT-6.1 Sol" };
const statusNames = {
  open: "待处理",
  paid: "已收款",
  refunded: "模拟退款已登记",
  settled: "已对账",
  new: "待受理",
  active: "处理中",
  waiting: "持续跟进",
  resolved: "已结案",
};
const eventNames = {
  confirm: "模拟确认数达标",
  topup: "模拟补足差额",
  verify_address: "模拟验证地址",
  approve: "模拟审批通过",
  clear_risk: "模拟解除风险",
  settle: "模拟结算到账",
};
const clone = (x) => structuredClone(x);
const $ = (selector) => document.querySelector(selector);
const workspace = () => workspaces.get(current);
const caseData = () => catalog.cases.find((c) => c.id === current);
const stageData = (id) => catalog.stages.find((s) => s.id === id);
const duration = (ms) =>
  ms == null
    ? "—"
    : ms >= 1000
      ? `${(ms / 1000).toFixed(2)} s`
      : `${ms.toFixed(1)} ms`;
const money = (value) =>
  Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

function fresh(snapshot) {
  return {
    snapshot: clone(snapshot),
    results: { decider: {}, bedrock: {} },
    audit: [],
    executions: {},
    activeExecution: null,
    revision: 1,
    runMode: null,
    decisionElapsedMs: null,
    workflowElapsedMs: null,
    conversation: [
      {
        kind: "customer",
        text: snapshot.message,
        revision: 1,
        time: new Date().toISOString(),
      },
    ],
  };
}

export async function mountCrypto(helpers) {
  ui = helpers;
  if (loaded || loading) return;
  loading = true;
  try {
    catalog = await ui.api("/api/crypto/catalog");
    catalog.cases.forEach((c) => workspaces.set(c.id, fresh(c.snapshot)));
    loaded = true;
    const root = $("#crypto-workspace");
    root.addEventListener("click", handleClick);
    root.addEventListener("change", handleChange);
    render();
  } catch (error) {
    $("#crypto-workspace").innerHTML =
      `<div class="result-error"><h3>工作台加载失败</h3><p>${ui.esc(error.message)}</p><button id="crypto-reload" class="secondary-button">重新加载</button></div>`;
    $("#crypto-reload").onclick = () => mountCrypto(helpers);
  } finally {
    loading = false;
  }
}

function addAudit(kind, text) {
  workspace().audit.push({ time: new Date().toISOString(), kind, text });
  workspace().audit = workspace().audit.slice(-80);
}

function addConversation(kind, text, extra = {}) {
  const w = workspace();
  w.conversation.push({
    kind,
    text,
    time: new Date().toISOString(),
    revision: w.revision,
    ...extra,
  });
  w.conversation = w.conversation.slice(-80);
}

function eventChange(event, before, after) {
  switch (event) {
    case "confirm":
      return `链上确认数 ${before.confirmations}/${before.required_confirmations} → ${after.confirmations}/${after.required_confirmations}`;
    case "topup":
      return `实际到账 ${money(before.received)} → ${money(after.received)} ${caseData().asset}；剩余差额 ${money(Math.max(0, Number(after.expected) - Number(after.received)))} ${caseData().asset}`;
    case "verify_address":
      return `退款地址 ${before.address_verified ? "已验证" : "未验证"} → ${after.address_verified ? "已验证" : "未验证"}`;
    case "approve":
      return `人工审批 ${before.approved ? "已通过" : "未通过"} → ${after.approved ? "已通过" : "未通过"}`;
    case "clear_risk":
      return `风险标记 ${before.risk_flag ? "有风险" : "无风险"} → ${after.risk_flag ? "有风险" : "无风险"}`;
    case "settle":
      return `商户结算 ${before.settled ? "已到账" : "未到账"} → ${after.settled ? "已到账" : "未到账"}`;
  }
}

function invalidate(message, event = "evidence") {
  const w = workspace();
  w.results = { decider: {}, bedrock: {} };
  w.executions = {};
  w.activeExecution = null;
  w.snapshot.completed = [];
  w.snapshot.review_pending = false;
  w.snapshot.order_status = "open";
  w.snapshot.ticket_status = "new";
  w.runMode = null;
  w.decisionElapsedMs = null;
  w.workflowElapsedMs = null;
  w.revision++;
  addAudit("event", message);
  addConversation(
    "event",
    `${message}\n旧决策和执行结果已清除。请点击「运行完整流程并对比」，按新证据继续处理。`,
    { event },
  );
}

function pairs() {
  const r = workspace().results;
  return catalog.stages
    .map(({ id }) => ({ id, a: r.decider[id], b: r.bedrock[id] }))
    .filter(
      ({ a, b }) =>
        a?.source === "live" &&
        b?.source === "live" &&
        a.input_hash === b.input_hash,
    );
}

function summary() {
  const matched = pairs();
  const same = matched.filter(({ a, b }) => a.choice === b.choice).length;
  const a = matched.reduce((n, row) => n + row.a.timings.backend_total_ms, 0);
  const b = matched.reduce((n, row) => n + row.b.timings.backend_total_ms, 0);
  const w = workspace();
  const replay = w.runMode === "replay";
  return `<div class="cx-summary">
    <div><span>当前案例 · 完整配对</span><strong>${matched.length}<small> / 5 步</small></strong></div>
    <div><span>两模型动作一致</span><strong>${matched.length ? `${same}/${matched.length}` : "—"}<small> 不是准确率</small></strong></div>
    <div><span>Decider 决策耗时合计</span><strong>${matched.length ? duration(a) : "—"}</strong></div>
    <div><span>GPT-6.1 Sol 决策耗时合计</span><strong>${matched.length ? duration(b) : "—"}</strong></div>
    <div class="cx-summary-note">${replay ? "当前为规则回放，所有结果均不计入模型性能统计。" : matched.length ? `只统计同一输入的成功配对。${a > 0 && b > a ? `本次 Bedrock / Decider 耗时比 ${(b / a).toFixed(1)}×。` : ""}这是单次观测，包含网络与排队。` : "运行真实对比后显示观测结果。失败、回放和不匹配的输入不会进入统计。"}</div>
  </div>`;
}

function comparisonTable() {
  const results = workspace().results;
  const cell = (r) =>
    r?.pending
      ? "运行中…"
      : r?.error
        ? '<span class="cx-table-error">调用失败</span>'
        : r?.choice
          ? `<strong>${ui.esc(r.label)}</strong><small>${r.source === "live" ? duration(r.timings.backend_total_ms) : "规则回放 · 未推理"}</small>`
          : '<span class="cx-table-empty">等待运行</span>';
  return `<div class="cx-table-wrap"><table class="cx-compare-table"><caption>逐步动作与实测耗时 · 点击步骤查看详细输出</caption><thead><tr><th>业务步骤</th><th>Strands Decider</th><th>GPT-6.1 Sol</th><th>本步对比</th></tr></thead><tbody>${catalog.stages
    .map((stage, index) => {
      const a = results.decider[stage.id],
        b = results.bedrock[stage.id];
      const paired =
        a?.source === "live" &&
        b?.source === "live" &&
        a.input_hash === b.input_hash;
      const label = paired
        ? a.choice === b.choice
          ? "动作一致"
          : "动作不同"
        : a?.source === "rule_replay" && b?.source === "rule_replay"
          ? "规则回放"
          : "未配对";
      return `<tr class="${stage.id === selectedStage ? "selected" : ""}"><th><button data-cx-stage="${stage.id}"><span>0${index + 1}</span>${ui.esc(stage.label)}</button></th><td>${cell(a)}</td><td>${cell(b)}</td><td><span class="cx-pair-badge ${paired && a.choice !== b.choice ? "different" : ""}">${label}</span></td></tr>`;
    })
    .join("")}</tbody></table></div>`;
}

function lane(provider) {
  const w = workspace(),
    results = w.results[provider],
    result = results[selectedStage];
  const successful = catalog.stages
    .map(({ id }) => results[id])
    .filter((r) => r?.choice);
  const live = successful.filter((r) => r.source === "live");
  const total = live.reduce((n, r) => n + r.timings.backend_total_ms, 0);
  const tokens = live.reduce(
    (n, r) => n + (r.usage?.input_tokens || 0) + (r.usage?.output_tokens || 0),
    0,
  );
  const title =
    provider === "decider"
      ? "专用决策模型 · 2B / CUDA"
      : "Bedrock · 美国推理配置 / low";
  let detail = `<div class="cx-result-empty">${ui.icon("route")}<strong>等待当前步骤的判断</strong><p>两侧收到相同证据与候选动作。</p></div>`;
  if (result?.pending)
    detail = `<div class="cx-result-empty cx-pending"><span class="cx-spinner"></span><strong>正在执行真实决策…</strong><p>结果会独立返回，另一侧无需等待。</p></div>`;
  else if (result?.error)
    detail = `<div class="cx-model-error"><strong>本步未获得模型结果</strong><p>${ui.esc(result.error)}</p><small>未用规则数据替代；本步不参与性能统计。</small></div>`;
  else if (result?.choice) {
    const distribution = result.probabilities
      ? `<div class="cx-distribution">${Object.entries(result.probabilities)
          .sort((a, b) => b[1] - a[1])
          .map(
            ([key, p]) =>
              `<div><span>${ui.esc(catalog.options[selectedStage][key])}</span><i><b style="width:${Math.max(0, Math.min(100, p * 100))}%"></b></i><small>${(p * 100).toFixed(1)}%</small></div>`,
          )
          .join("")}</div>`
      : `<p class="cx-model-note">${result.source === "live" ? "GPT 返回候选动作 JSON，不提供可与 Decider 比较的校准概率。" : "确定性规则回放，没有模型概率或推理时间。"}</p>`;
    detail = `<div class="cx-decision ${result.matches_reference ? "match" : "mismatch"}"><span>${result.source === "live" ? "真实模型建议" : "规则回放 · 非模型输出"}</span><h3>${ui.esc(result.label)}</h3><p>${result.matches_reference ? "与演示参考一致" : `与演示参考不同：${ui.esc(result.reference_label)}`}</p></div>
      <div class="cx-detail-metrics"><div><span>本步后端总耗时</span><b>${duration(result.timings?.backend_total_ms)}</b></div><div><span>浏览器往返</span><b>${result.source === "live" ? duration(result.client_ms) : "未推理"}</b></div><div><span>${provider === "decider" ? "归一化 confidence" : "输入 / 输出 tokens"}</span><b>${provider === "decider" ? (result.confidence == null ? "—" : result.confidence.toFixed(3)) : result.usage ? `${result.usage.input_tokens} / ${result.usage.output_tokens}` : "—"}</b></div></div>
      ${distribution}<details class="cx-raw"><summary>查看原始响应与输入指纹</summary><pre>${ui.esc(JSON.stringify(result, null, 2))}</pre></details>`;
  }
  return `<section class="cx-lane ${provider}" aria-label="${providerNames[provider]} 对比结果">
    <div class="cx-lane-head"><div class="cx-model-mark">${provider === "decider" ? "D" : "G"}</div><div><h3>${providerNames[provider]}</h3><span>${title}</span></div><b class="cx-model-count">${successful.length}/5</b></div>
    <div class="cx-lane-totals"><span>实测合计 <b>${live.length ? duration(total) : "—"}</b></span><span>参考一致 <b>${live.length ? `${live.filter((r) => r.matches_reference).length}/${live.length}` : "—"}</b></span><span>${provider === "bedrock" ? `tokens <b>${live.length ? tokens : "—"}</b>` : "GPU 按运行小时计费"}</span></div>
    <div class="cx-lane-steps">${catalog.stages
      .map((stage, i) => {
        const r = results[stage.id];
        return `<button data-cx-stage="${stage.id}" class="${stage.id === selectedStage ? "selected" : ""} ${r?.choice ? "done" : r?.error ? "failed" : ""}" title="${ui.esc(stage.label)}"><span>${r?.pending ? "…" : r?.choice ? "✓" : r?.error ? "!" : i + 1}</span><small>${ui.esc(stage.label)}</small></button>`;
      })
      .join("")}</div>
    <div class="cx-lane-detail">${detail}</div>
    <div class="cx-lane-footer"><small>每步执行结果与最终业务结果见上方展开区域。</small></div>
  </section>`;
}

function executionOutput(record) {
  if (record.error) return `执行请求失败：${record.error}。本步未确认完成。`;
  if (!record.applied) return record.message;
  const s = record.snapshot,
    c = caseData();
  switch (record.stage) {
    case "intake":
      return `工单 ${c.ticket_id} 已受理，分类为「${record.label}」；工单状态：${statusNames[s.ticket_status]}。`;
    case "verify":
      return s.scenario === "settlement"
        ? `结算 ${s.settled ? "已到账" : "未到账"}；耗时 ${s.settlement_minutes} 分钟 / SLA ${s.settlement_sla_minutes} 分钟。本次选择：${record.label}。`
        : `应付 ${money(s.expected)} ${c.asset}，到账 ${money(s.received)} ${c.asset}，差额 ${money(Math.max(0, Number(s.expected) - Number(s.received)))} ${c.asset}；链上确认 ${s.confirmations}/${s.required_confirmations}。本次选择：${record.label}。`;
    case "approve":
      return `${s.risk_flag ? "有风险标记，需要人工复核" : "无风险标记"}${s.scenario === "refund" ? `；退款地址${s.address_verified ? "已验证" : "未验证"}；人工审批${s.approved ? "已通过" : "未通过"}` : ""}。处理结论：${record.label}。`;
    case "execute":
      return record.ledger_entry
        ? `已登记模拟账本：${record.label} ${money(record.ledger_entry.amount)} ${c.asset}；订单状态：${statusNames[s.order_status]}。未发送资金。`
        : `已采用「${record.label}」；订单状态：${statusNames[s.order_status]}。未生成资金账本记录。`;
    case "close":
      return `工单状态：${statusNames[s.ticket_status]}。客服回复：${record.customer_reply}`;
    default:
      return record.message;
  }
}

function finalOutcome(provider) {
  const w = workspace(),
    execution = w.executions[provider];
  const records = execution?.audit || [];
  const completed = execution?.snapshot.completed.length || 0;
  const allDone = catalog.stages.every(
    ({ id }) => w.results[provider][id]?.choice,
  );
  const failed = catalog.stages.some(
    ({ id }) => w.results[provider][id]?.error,
  );
  const reply = records.findLast((r) => r.customer_reply)?.customer_reply;
  const ledger = records.filter((r) => r.ledger_entry);
  const adjustments = records.filter((r) => r.safety_adjusted).length;
  const differences = records.filter((r) => r.policy_warning).length;
  const interrupted =
    execution && !execution.finished && !execution.runningStage;
  const state = execution?.blocked
    ? "blocked"
    : execution?.error
      ? "error"
      : execution?.finished
        ? "finished"
        : "waiting";
  const title = execution?.blocked
    ? "步骤未完成 · 已暂停"
    : execution?.error
      ? "执行失败 · 未完成"
      : execution?.finished
        ? `${statusNames[execution.snapshot.ticket_status]} · ${statusNames[execution.snapshot.order_status]}`
        : execution?.runningStage
          ? "沙盒执行中"
          : interrupted
            ? "流程已暂停"
            : "尚未执行";
  const description = execution?.blocked
    ? "后端未接受当前步骤，请刷新页面后重试。"
    : execution?.error
      ? execution.error
      : execution?.finished
        ? execution.snapshot.ticket_status === "resolved"
          ? "五步已完成，业务已在沙盒中结案。"
          : "五步已完成，业务仍待跟进；可补齐交易证据或完成方案要求的人工复核后重新演练。"
        : interrupted
          ? "已保留完成的步骤，可继续执行剩余步骤。"
          : execution?.runningStage
            ? `正在执行「${stageData(execution.runningStage).label}」。`
            : failed
              ? "模型调用失败，尚未获得完整方案，本侧没有执行业务步骤。"
              : allDone
                ? "已生成五步建议。点击下方按钮执行，或运行上方完整流程同时查看两侧结果。"
                : "点击「运行完整流程并对比」，依次生成建议并执行两套独立沙盒流程。";
  return `<article class="cx-final-card ${provider}" data-cx-final="${provider}">
    <div class="cx-final-heading"><strong>${providerNames[provider]}</strong><span>${w.runMode === "replay" ? "规则回放 · " : ""}已执行 ${completed}/5 步</span></div>
    <div class="cx-outcome ${state}"><strong>${ui.esc(title)}</strong><p>${ui.esc(description)}</p></div>
    ${differences || adjustments ? `<p class="cx-policy-summary">参考差异 ${differences} 步 · 保护调整 ${adjustments} 步。原始模型建议均保留，参考差异不暂停流程。</p>` : ""}
    <dl class="cx-final-facts"><div><dt>订单 ${ui.esc(caseData().order_id)}</dt><dd>${execution ? ui.esc(statusNames[execution.snapshot.order_status]) : "未更新"}</dd></div><div><dt>客服工单 ${ui.esc(caseData().ticket_id)}</dt><dd>${execution ? ui.esc(statusNames[execution.snapshot.ticket_status]) : "未更新"}</dd></div><div><dt>模拟账本</dt><dd>${ledger.length ? ledger.map((r) => `${ui.esc(r.label)} · ${money(r.ledger_entry.amount)} ${ui.esc(caseData().asset)}`).join("；") : "无资金记录"}</dd></div></dl>
    <div class="cx-final-reply"><span>最终客服回复</span><p>${ui.esc(reply || "尚未执行回复结案步骤，没有发送客服回复。")}</p></div>
    <small class="cx-execution-time">沙盒执行往返合计：${duration(execution?.elapsedMs)} · 不计入模型推理时间</small>
    <div class="cx-final-actions"><button data-cx-apply="${provider}" class="secondary-button" ${busy || !allDone || execution?.finished ? "disabled" : ""}>${execution?.finished ? "已完成沙盒流程" : execution ? "继续采用建议" : "采用此方案 · 模拟执行"}</button></div>
  </article>`;
}

function stepExecution(provider, stage) {
  const w = workspace(),
    result = w.results[provider][stage.id],
    execution = w.executions[provider];
  const records = execution?.audit.filter((r) => r.stage === stage.id) || [];
  const latest = records.at(-1);
  const running = execution?.runningStage === stage.id;
  const state = running
    ? "running"
    : latest?.error
      ? "error"
      : latest?.applied
        ? "done"
        : latest
          ? "blocked"
          : "waiting";
  const status = running
    ? "执行中"
    : latest?.error
      ? "执行失败"
      : latest?.applied
        ? latest.safety_adjusted
          ? "保护调整 · 已完成"
          : latest.policy_warning
            ? "已执行 · 有参考差异"
            : "已执行"
        : latest
          ? "已拦截"
          : execution?.blocked || execution?.error
            ? "前序中断 · 未执行"
            : "未执行";
  let output = result?.error
    ? `模型调用失败：${result.error}。没有执行此步骤。`
    : result?.pending
      ? "正在等待决策结果。"
      : execution?.blocked || execution?.error
        ? "前序步骤未通过，当前步骤没有执行。"
        : result?.choice
          ? "已获得建议，尚未执行此步骤。"
          : "运行后显示本步决策与执行输出。";
  if (latest) output = executionOutput(latest);
  if (running) output = "正在提交沙盒动作，等待服务端执行结果。";
  return `<div class="cx-step-result ${provider} ${state}" data-cx-result="${provider}-${stage.id}">
    <div class="cx-step-result-head"><strong>${providerNames[provider]}</strong><span class="cx-execution-badge">${status}</span></div>
    <p class="cx-step-choice"><span>${result?.source === "rule_replay" ? "规则回放建议" : "模型建议"}</span><b>${ui.esc(result?.label || (result?.error ? "调用失败" : result?.pending ? "判断中…" : "等待运行"))}</b></p>
    ${result?.choice ? `<div class="cx-step-reference ${result.matches_reference ? "" : "different"}">${result.matches_reference ? "与演示参考一致" : `与演示参考不同 · 参考建议「${ui.esc(result.reference_label)}」`}</div>` : ""}
    <p class="cx-step-output">${ui.esc(output)}</p>
    ${latest?.safety_adjusted ? `<p class="cx-step-correction">保护调整：${ui.esc(latest.requested_label)} → ${ui.esc(latest.label)}。${ui.esc(latest.safety_reason)}（原始模型建议保留，不计作模型判断正确）</p>` : latest?.policy_warning ? `<p class="cx-step-correction">${ui.esc(latest.policy_warning)}</p>` : ""}
    ${records
      .slice(0, -1)
      .map(
        (r) =>
          `<p class="cx-step-attempt">此前${r.error ? "请求失败" : r.applied ? "执行" : "拦截"}：${ui.esc(r.label || "")} · ${ui.esc(r.error || r.message)}</p>`,
      )
      .join("")}
    <div class="cx-step-timing"><span>决策：${result?.source === "live" ? duration(result.timings?.backend_total_ms) : result?.source === "rule_replay" ? "规则回放 · 未推理" : "—"}</span><span>执行往返：${duration(latest?.elapsed_ms)}</span>${latest?.completed_at ? `<time datetime="${ui.esc(latest.completed_at)}">${latest.applied ? "完成于" : "记录于"} ${new Date(latest.completed_at).toLocaleTimeString("zh-CN", { hour12: false })}</time>` : ""}</div>
  </div>`;
}

function renderExecutionResults() {
  const w = workspace();
  return `<section class="cx-execution-results" id="cx-execution-results" aria-label="逐步执行结果与最终结果">
    <div class="cx-results-heading"><h2>最终业务结果</h2><p>两侧使用独立的模拟订单与账本。完成五步后，工单可能结案，也可能持续跟进。</p></div>
    <div class="cx-final-grid">${providers.map(finalOutcome).join("")}</div>
    <div class="cx-workflow-timing"><span>五步决策对比 · 浏览器经过时间 <b>${duration(w.decisionElapsedMs)}</b></span><span>本轮一键流程（含决策、执行及保护调整）· 浏览器经过时间 <b>${duration(w.workflowElapsedMs)}</b></span></div>
    <div class="cx-results-heading"><h2>每一步的执行结果</h2><p>每步展示模型建议与实际执行；参考差异仅作提示，资金保护调整会单独标注。</p></div>
    <div class="cx-execution-steps">${catalog.stages.map((stage, i) => `<section class="cx-execution-step" aria-label="${ui.esc(stage.label)} 执行输出"><div class="cx-execution-step-heading"><h3><span>0${i + 1}</span>${ui.esc(stage.label)}</h3><code>沙盒 · ${ui.esc(stage.tool)}</code></div><div class="cx-step-pair">${providers.map((p) => stepExecution(p, stage)).join("")}</div></section>`).join("")}</div>
  </section>`;
}

function renderConversation() {
  const c = caseData(),
    w = workspace();
  const events =
    current === "settlement"
      ? ["settle", "clear_risk"]
      : current === "refund"
        ? ["verify_address", "approve", "clear_risk"]
        : ["confirm", "topup", "clear_risk"];
  const history = w.conversation
    .map((entry) => {
      const stamp = `证据 v${entry.revision} · ${new Date(entry.time).toLocaleTimeString("zh-CN", { hour12: false })}`;
      const text = ui.esc(entry.text).replaceAll("\n", "<br>");
      if (entry.kind === "event")
        return `<div class="cx-system-message ${entry.failed ? "failed" : ""}" data-cx-event-notice="${ui.esc(entry.event)}"><small>系统通知 · ${stamp}</small><strong>${entry.failed ? "模拟事件未执行" : entry.event === "evidence" ? "业务证据已更新" : "模拟交易已推进"}</strong><p>${text}</p></div>`;
      const isReply = entry.kind === "reply";
      return `<div class="cx-bubble ${isReply ? "agent" : "customer"}"><small>${isReply ? `模拟客服 · ${providerNames[entry.provider]} · ${entry.mode === "replay" ? "规则回放" : "真实模型决策"}` : "客户诉求"}<br>${stamp}${entry.revision < w.revision ? " · 历史记录" : ""}</small><p>${text}</p></div>`;
    })
    .join("");
  return `<section class="cx-card cx-conversation">
    <div class="cx-card-heading"><h3>${ui.icon("message")}客服会话</h3><span>${ui.esc(c.ticket_id)}</span></div>
    <div class="cx-chat-person"><span class="cx-avatar">${ui.esc(c.customer[0])}</span><div><strong>${ui.esc(c.customer)}</strong><small>订单 ${ui.esc(c.order_id)}</small></div><span class="cx-dot"></span></div>
    <div class="cx-chat" aria-label="客户诉求、模拟交易事件与客服回复记录">${history}
    ${!w.conversation.some((entry) => entry.kind === "reply") ? `<p class="cx-chat-hint">模拟交易事件会立即出现在这里。运行完整流程后，继续显示两侧客服回复。</p>` : ""}
    </div>
    <div class="cx-events"><strong>推进模拟交易</strong><span>点击后在上方会话查看证据变化，再重新运行流程。</span>${events.map((event) => `<button class="cx-event-button" data-cx-event="${event}" ${busy ? "disabled" : ""}>${ui.icon("plus")}${eventNames[event]}</button>`).join("")}</div>
    <label class="cx-field">修改客户诉求<textarea id="cx-message" maxlength="1800" rows="3" ${busy ? "disabled" : ""}>${ui.esc(w.snapshot.message)}</textarea></label>
    <button data-cx-save-message class="secondary-button" ${busy ? "disabled" : ""}>更新诉求并重新核验</button>
    <small class="cx-note">事件为模拟系统通知，回复来自话术模板。保留最近 80 条会话；历史回复标注证据版本，刷新或退出后清除。</small>
  </section>`;
}

function renderAudit() {
  const w = workspace();
  const ledger = Object.entries(w.executions).flatMap(([provider, execution]) =>
    execution.audit
      .filter((a) => a.ledger_entry)
      .map((a) => ({ provider, ...a.ledger_entry })),
  );
  return `<section class="cx-card cx-audit"><div class="cx-card-heading"><h3>${ui.icon("history")}处置记录与模拟账本</h3><span>${w.audit.length} 条记录</span></div>
    ${ledger.length ? `<div class="cx-ledger">${ledger.map((row) => `<div><span>${ui.icon("check-circle")} ${ui.esc(catalog.options.execute[row.type])}</span><b>${money(row.amount)} ${ui.esc(caseData().asset)}</b><small>${providerNames[row.provider]} · 模拟记录，无链上交易</small></div>`).join("")}</div>` : ""}
    <div class="cx-audit-list">${
      w.audit.length
        ? [...w.audit]
            .reverse()
            .map(
              (row) =>
                `<div class="cx-audit-row ${row.kind}"><time>${new Date(row.time).toLocaleTimeString("zh-CN", { hour12: false })}</time><i></i><p>${ui.esc(row.text)}</p></div>`,
            )
            .join("")
        : `<div class="cx-empty-audit">从运行模型对比开始。核验、审批、参考差异、保护调整与模拟记账会逐条出现在这里。</div>`
    }</div>
  </section>`;
}

function render() {
  if (!loaded) return;
  const c = caseData(),
    w = workspace(),
    s = w.snapshot,
    e = ui.esc;
  const disabled = busy ? "disabled" : "";
  $("#crypto-workspace").innerHTML = `
    <div class="cx-heading"><div><div class="eyebrow"><span></span> PAYMENT OPERATIONS LAB</div><h1>一笔支付，走完每一步<span class="heading-dot">。</span></h1><p>从客户消息到交易核验、审批与结案，观察两种模型如何推动同一笔业务。</p></div><span class="cx-sandbox">${ui.icon("layers")}业务沙盒 · 不发送资金</span></div>
    <div class="cx-hero"><div><span class="cx-live-dot"></span><strong>Decider × GPT-6.1 Sol</strong><span>相同业务事实 · 相同候选动作 · 独立实测</span></div><div class="cx-hero-actions"><button class="text-button" data-cx-reset ${disabled}>重置案例</button><button class="text-button" data-cx-export ${disabled}>${ui.icon("copy")}导出记录</button></div></div>
    <div class="cx-workspace">
      <aside class="cx-inbox"><div class="cx-inbox-title"><h2>业务场景</h2><span>04</span></div>${catalog.cases.map((item, i) => `<button class="cx-case ${item.id === current ? "active" : ""}" data-cx-case="${item.id}" ${disabled}><div><span>${String(i + 1).padStart(2, "0")} / ${e(item.category)}</span><i>${ui.icon(item.id === "refund" ? "rotate" : item.id === "settlement" ? "layers" : "route")}</i></div><strong>${e(item.title)}</strong><small>${e(item.asset)} · ${e(item.network)}</small></button>`).join("")}<div class="cx-inbox-foot">${ui.icon("lightbulb")}改变交易证据，再观察处理路径如何变化。</div></aside>
      <div class="cx-case-main"><section class="cx-card cx-order"><div class="cx-card-heading"><div><span class="tiny-label">${e(c.order_id)} · ${e(c.merchant)}</span><h2>${e(c.title)}</h2></div><span class="cx-state-tag">证据版本 v${w.revision}</span></div>
        <p class="cx-case-description">${e(c.summary)}</p><div class="cx-order-metrics"><div><span>应付金额</span><strong>${money(s.expected)} <small>${e(c.asset)}</small></strong></div><div><span>实际到账</span><strong>${money(s.received)} <small>${e(c.asset)}</small></strong></div><div><span>${current === "settlement" ? "结算耗时 / SLA" : "链上确认"}</span><strong>${current === "settlement" ? `${s.settlement_minutes} / ${s.settlement_sla_minutes}` : `${s.confirmations} / ${s.required_confirmations}`}<small>${current === "settlement" ? " min" : " 次"}</small></strong></div></div>
        <div class="cx-fact-chips"><span class="${Number(s.received) >= Number(s.expected) ? "ok" : "warn"}">差额 ${money(Math.max(0, Number(s.expected) - Number(s.received)))}</span><span class="${s.risk_flag ? "warn" : "ok"}">${s.risk_flag ? "待人工风控" : "无风险标记"}</span>${current === "refund" ? `<span class="${s.address_verified ? "ok" : "warn"}">${s.address_verified ? "地址已验证" : "地址未验证"}</span><span class="${s.approved ? "ok" : "warn"}">${s.approved ? "审批已通过" : "待人工审批"}</span>` : ""}${current === "settlement" ? `<span class="${s.settled ? "ok" : "warn"}">${s.settled ? "结算已到账" : "结算未到账"}</span>` : ""}</div>
        <details class="cx-evidence"><summary>${ui.icon("sliders")}编辑业务证据</summary><div class="cx-evidence-fields">
          <label>应付金额<input type="number" min="0.01" max="1000000" step="0.01" data-cx-field="expected" value="${e(s.expected)}" ${disabled}></label>
          <label>实际到账<input type="number" min="0" max="1000000" step="0.01" data-cx-field="received" value="${e(s.received)}" ${disabled}></label>
          <label>确认数<input type="number" min="0" max="1000" step="1" data-cx-field="confirmations" value="${s.confirmations}" ${disabled}></label>
          <label>结算耗时（分钟）<input type="number" min="0" max="10080" step="1" data-cx-field="settlement_minutes" value="${s.settlement_minutes}" ${disabled}></label>
          <label class="cx-check"><input type="checkbox" data-cx-field="risk_flag" ${s.risk_flag ? "checked" : ""} ${disabled}>风险标记，需要人工复核</label>
        </div><p>金额差额与是否满足门槛由后端计算。更改证据会清除旧模型结果，重新开始审批流程。</p></details>
      </section>
      <section class="cx-card cx-flow"><div class="cx-card-heading"><h3>端到端业务流程</h3><span>05 STEPS</span></div><div class="cx-flow-track">${catalog.stages.map((stage, i) => `<button data-cx-stage="${stage.id}" class="${stage.id === selectedStage ? "active" : ""}"><span>${i + 1}</span><strong>${e(stage.label)}</strong><small>${e(stage.tool.split(".")[0])}</small></button>`).join("")}</div><div class="cx-stage-caption"><strong>${e(stageData(selectedStage).label)}</strong><span>${e(stageData(selectedStage).description)}</span><code>${e(stageData(selectedStage).tool)}</code></div></section></div>
      ${renderConversation()}
    </div>
    <section class="cx-comparison" aria-label="Bedrock 与 Decider 对比"><div class="cx-comparison-heading"><div><h2>同案对比，看到真实差异</h2><p>参考动作只用于对比，不再因选择不同而暂停；资金条件未满足时挂起资金动作，继续完成流程。</p></div><div class="cx-controls"><div class="mode-switch" role="group" aria-label="支付模块运行模式"><button data-cx-mode="live" class="${mode === "live" ? "active" : ""}" ${disabled}>真实模型</button><button data-cx-mode="replay" class="${mode === "replay" ? "active" : ""}" ${disabled}>规则回放</button></div><button data-cx-run="step" class="secondary-button" ${disabled}>对比当前步骤</button><button data-cx-run="all" class="secondary-button" ${disabled}>仅对比 5 步决策</button><button data-cx-run="workflow" class="primary-button" ${disabled}>${ui.icon("play")}运行完整流程并对比</button>${busy ? `<button data-cx-stop class="text-button">${stopRequested ? "当前步骤后停止…" : "停止后续步骤"}</button>` : ""}</div></div>
      <div id="cx-run-status" class="cx-run-status" role="status">${busy ? `${ui.icon("refresh")}正在处理「${e(stageData(selectedStage).label)}」，每侧结果独立返回。` : w.runMode === "replay" ? "规则回放 · 不调用模型，不展示虚构的耗时或 token。" : "真实调用 GPT-6.1 Sol（low）与 SageMaker Decider v19。客服话术与业务执行不计入模型决策耗时。"}</div>
      ${summary()}${comparisonTable()}${renderExecutionResults()}<h2 class="cx-diagnostics-heading">决策详情 · ${e(stageData(selectedStage).label)}</h2><div class="cx-lanes">${lane("decider")}${lane("bedrock")}</div>
      <p class="cx-comparison-foot">各步骤按顺序运行，同一步的两模型并发调用。耗时合计仅累计成功的配对决策，非整条业务流程的墙钟时间。${e(catalog.price_note)}</p>
    </section>
    ${renderAudit()}
    <div class="cx-page-note">演练数据保存在当前页面内存中，刷新或退出后清除。模型结果、规则回放、参考差异与保护调整均分别标记，可导出复核。</div>`;
  const chat = $(".cx-chat");
  if (chat) chat.scrollTop = chat.scrollHeight;
}

async function run(which) {
  if (busy) return;
  busy = true;
  stopRequested = false;
  const w = workspace(),
    snapshot = clone(w.snapshot),
    runMode = mode;
  const complete = which !== "step";
  const stages = complete ? catalog.stages.map((s) => s.id) : [selectedStage];
  if (w.runMode !== runMode || complete)
    w.results = { decider: {}, bedrock: {} };
  w.runMode = runMode;
  w.executions = {};
  w.activeExecution = null;
  w.decisionElapsedMs = null;
  w.workflowElapsedMs = null;
  const started = performance.now();
  addAudit(
    "run",
    `${runMode === "live" ? "真实模型" : "规则回放"} · 开始${complete ? "五步决策" : stageData(selectedStage).label}对比，证据 v${w.revision}。`,
  );
  try {
    for (const stage of stages) {
      if (stopRequested) break;
      selectedStage = stage;
      providers.forEach((p) => {
        w.results[p][stage] = { pending: true };
      });
      render();
      await Promise.allSettled(
        providers.map(async (provider) => {
          const t = performance.now();
          try {
            const result = await ui.api("/api/crypto/decision", {
              snapshot,
              stage,
              provider,
              mode: runMode,
              model_id: "us.openai.gpt-6.1-sol",
            });
            result.client_ms =
              runMode === "live" ? performance.now() - t : null;
            w.results[provider][stage] = result;
            addAudit(
              result.matches_reference ? "decision" : "warning",
              `${providerNames[provider]} · ${stageData(stage).label} → ${result.label}${result.source !== "live" ? "（规则回放）" : ""}${!result.matches_reference ? "；与演示参考不同（不因此暂停）" : ""}`,
            );
          } catch (error) {
            w.results[provider][stage] = { error: error.message };
            addAudit(
              "error",
              `${providerNames[provider]} · ${stageData(stage).label}失败：${error.message}`,
            );
          }
          render();
        }),
      );
    }
    addAudit(
      "run",
      `${stopRequested ? "已停止后续步骤" : "本轮对比完成"}。浏览器整轮经过 ${duration(performance.now() - started)}，包含并发调用、网络和页面处理。`,
    );
    if (complete && !stopRequested)
      w.decisionElapsedMs = performance.now() - started;
    if (which === "workflow") {
      for (const provider of providers) {
        if (stopRequested) break;
        if (catalog.stages.every(({ id }) => w.results[provider][id]?.choice))
          await executePlan(provider);
      }
      if (!stopRequested) w.workflowElapsedMs = performance.now() - started;
    }
  } finally {
    busy = false;
    stopRequested = false;
    render();
    if (which === "workflow")
      $("#cx-execution-results").scrollIntoView({ block: "start" });
  }
}

async function execute(provider) {
  if (busy) return;
  const w = workspace();
  if (!catalog.stages.every(({ id }) => w.results[provider][id]?.choice))
    return;
  busy = true;
  stopRequested = false;
  try {
    await executePlan(provider);
  } finally {
    busy = false;
    stopRequested = false;
    render();
  }
}

async function executePlan(provider) {
  const w = workspace();
  w.activeExecution = provider;
  const execution = (w.executions[provider] ||= {
    snapshot: clone(w.snapshot),
    audit: [],
    finished: false,
    blocked: false,
    error: null,
    runningStage: null,
    elapsedMs: 0,
  });
  execution.blocked = false;
  execution.error = null;
  render();
  try {
    for (const stage of catalog.stages) {
      if (stopRequested) break;
      if (execution.snapshot.completed.includes(stage.id)) continue;
      selectedStage = stage.id;
      const result = w.results[provider][stage.id];
      const choice = result.choice;
      execution.runningStage = stage.id;
      render();
      const started = performance.now();
      let applied;
      try {
        applied = await ui.api("/api/crypto/apply", {
          snapshot: execution.snapshot,
          stage: stage.id,
          choice,
        });
      } catch (error) {
        const elapsed = performance.now() - started;
        execution.elapsedMs += elapsed;
        execution.audit.push({
          stage: stage.id,
          action: choice,
          label: catalog.options[stage.id][choice],
          error: error.message,
          elapsed_ms: elapsed,
          completed_at: new Date().toISOString(),
        });
        throw error;
      }
      const elapsed = performance.now() - started;
      execution.elapsedMs += elapsed;
      execution.audit.push({
        stage: stage.id,
        elapsed_ms: elapsed,
        completed_at: new Date().toISOString(),
        ...applied,
      });
      execution.runningStage = null;
      execution.snapshot = applied.snapshot;
      if (applied.applied && applied.customer_reply)
        addConversation("reply", applied.customer_reply, {
          provider,
          mode: w.runMode,
        });
      addAudit(
        applied.safety_adjusted || applied.policy_warning
          ? "warning"
          : applied.applied
            ? "applied"
            : "error",
        `${providerNames[provider]}${applied.safety_adjusted ? " / 资金与结案保护调整" : ""} · ${stage.label}：${applied.label}。${applied.message}`,
      );
      if (!applied.applied) {
        execution.blocked = true;
        break;
      }
      render();
    }
    execution.finished = execution.snapshot.completed.length === 5;
    if (execution.finished)
      addAudit(
        "applied",
        `${providerNames[provider]} 沙盒流程完成：${statusNames[execution.snapshot.ticket_status]} / ${statusNames[execution.snapshot.order_status]}。`,
      );
  } catch (error) {
    execution.error = error.message;
    addAudit("error", `模拟执行失败：${error.message}`);
    ui.toast(error.message);
  } finally {
    execution.runningStage = null;
    render();
  }
}

async function handleClick(event) {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  if (button.hasAttribute("data-cx-stop")) {
    stopRequested = true;
    button.textContent = "当前步骤后停止…";
    return;
  }
  if (button.dataset.cxStage) {
    if (!busy) {
      selectedStage = button.dataset.cxStage;
      render();
    }
    return;
  }
  if (busy) return;
  if (button.hasAttribute("data-cx-reset")) {
    workspaces.set(current, fresh(caseData().snapshot));
    selectedStage = "intake";
    render();
    return;
  }
  if (button.dataset.cxCase) {
    current = button.dataset.cxCase;
    selectedStage = "intake";
    render();
    return;
  }
  if (button.dataset.cxMode) {
    mode = button.dataset.cxMode;
    render();
    return;
  }
  if (button.dataset.cxRun) {
    await run(button.dataset.cxRun);
    return;
  }
  if (button.dataset.cxApply) {
    await execute(button.dataset.cxApply);
    return;
  }
  if (button.hasAttribute("data-cx-save-message")) {
    const value = $("#cx-message").value.trim();
    if (!value) {
      ui.toast("请先输入客户诉求。");
      return;
    }
    workspace().snapshot.message = value;
    addConversation("customer", value, { revision: workspace().revision + 1 });
    invalidate("客户诉求已更新，旧判断已清除。");
    render();
  }
  if (button.dataset.cxEvent) {
    const simulationEvent = button.dataset.cxEvent;
    const before = clone(workspace().snapshot);
    busy = true;
    render();
    try {
      const result = await ui.api("/api/crypto/event", {
        snapshot: workspace().snapshot,
        event: simulationEvent,
      });
      workspace().snapshot = result.snapshot;
      invalidate(
        `${eventNames[simulationEvent]}：${eventChange(simulationEvent, before, result.snapshot)}。`,
        simulationEvent,
      );
    } catch (error) {
      addConversation(
        "event",
        `${eventNames[simulationEvent]}：${error.message}。交易证据未改变。`,
        { event: simulationEvent, failed: true },
      );
      addAudit(
        "error",
        `${eventNames[simulationEvent]}未执行：${error.message}`,
      );
      ui.toast(error.message);
    } finally {
      busy = false;
      render();
      $(".cx-chat")?.scrollIntoView({ block: "nearest" });
    }
  }
  if (button.hasAttribute("data-cx-export")) {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            exported_at: new Date().toISOString(),
            case: caseData(),
            ...workspace(),
            note: "模拟业务流程；参考一致率不是通用准确率。未执行真实资金操作。",
            models: {
              decider: "Strands Decider v19",
              bedrock: "us.openai.gpt-6.1-sol",
              reasoning: "low",
            },
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `payment-workflow-${current}-v${workspace().revision}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function handleChange(event) {
  const field = event.target.dataset.cxField;
  if (!field || busy) return;
  if (!event.target.checkValidity() || event.target.value === "") {
    ui.toast("请输入范围内的有效数值，业务证据未修改。");
    event.target.value = workspace().snapshot[field];
    return;
  }
  workspace().snapshot[field] =
    event.target.type === "checkbox"
      ? event.target.checked
      : ["expected", "received"].includes(field)
        ? event.target.value
        : Number(event.target.value);
  invalidate("业务证据已修改，旧模型结果与模拟执行状态已清除。");
  render();
}
