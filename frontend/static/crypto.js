let ui,
  catalog,
  current = "pending",
  loaded = false,
  loading = false;
let busy = false,
  stopRequested = false,
  mode = "live",
  selectedStage = "intake";
let autoEvents = true;
let testKind = "workflow";
const workflowNames = {
  fixed: "固定流程",
  optimized: "优化流程",
  loop: "自主闭环",
};
const expandedPanels = new Set();
const panelOpen = (name) => (expandedPanels.has(name) ? "open" : "");
const workspaces = new Map();
const providers = ["decider", "bedrock"];
const providerNames = { decider: "Strands Decider", bedrock: "GPT-6.1 Sol" };
const caseNames = {
  pending: "USDC 未到账",
  underpaid: "USDT 少付",
  refund: "稳定币退款",
  settlement: "商户结算",
};
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
    workflowKind: "fixed",
    dialogues: [],
    dialogueRun: 0,
    viewedDialogueRun: 0,
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
    window.addEventListener("decider-gpu-state", renderGpuNotice);
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

function renderGpuNotice() {
  const root = $("#cx-gpu-notice");
  if (!root || !ui?.gpu) return;
  const { state: s, error } = ui.gpu();
  if (s && !s.enabled && !error) {
    root.hidden = true;
    return;
  }
  root.hidden = false;
  const ready = s?.phase === "ready" && s.desired === "running" && !error;
  const title = error
    ? "GPU 状态暂不可用"
    : !s
      ? "正在检查 Decider GPU"
      : ready
        ? "Decider GPU 已就绪"
        : {
            stopped: "Decider GPU 未启动",
            starting: "Decider GPU 启动中",
            stopping: "Decider GPU 正在停止",
            error: "Decider GPU 启动未完成",
          }[s.phase] || "Decider GPU 尚未就绪";
  const message = error
    ? `${error}。请刷新状态后再运行真实模型。`
    : ready
      ? s.idle_auto_stop === false
        ? "GPU 持续运行"
        : `闲置 ${s.idle_minutes ?? 30} 分钟自动停止`
      : s?.phase === "starting"
        ? "正在分配实例、加载模型，请等待就绪。"
        : s?.phase === "stopping"
          ? "正在停止；规则回放仍可运行。"
          : s?.phase === "error"
            ? `${s.last_error_message || "GPU 未在时限内就绪"}。可重新启动或使用规则回放。`
            : s?.enabled
              ? s.can_manage
                ? "先启动 GPU，或选择规则回放。"
                : "请联系管理员启动 GPU。"
              : "正在读取状态";
  root.className = `cx-gpu-notice ${ready ? "ready" : "pending"}`;
  root.innerHTML = `<div><strong>${ui.esc(title)}</strong><span>${ui.esc(message)}</span></div><button data-cx-gpu-open class="text-button">GPU 管理</button>`;
}

async function gpuReady(runMode = mode) {
  if (runMode !== "live") return true;
  return ui.ensureGpuReady("支付流程对比");
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
  w.workflowKind = "fixed";
  w.revision++;
  addAudit("event", message);
  addConversation("event", `${message}\n点击「开始对比」，按新证据重新运行。`, {
    event,
  });
}

function pairs() {
  const r = workspace().results;
  return catalog.stages
    .map(({ id }) => ({ id, a: r.decider[id], b: r.bedrock[id] }))
    .filter(
      ({ a, b }) =>
        a?.source === "live" &&
        b?.source === "live" &&
        a.input_profile === b.input_profile &&
        a.input_hash === b.input_hash,
    );
}

function summary() {
  const w = workspace(),
    loop = w.workflowKind === "loop",
    paired = pairs();
  const rows = Object.fromEntries(
    providers.map((provider) => [
      provider,
      loop
        ? (w.executions[provider]?.decisionHistory || []).filter(
            (r) => r.source === "live",
          )
        : paired.map((row) => (provider === "decider" ? row.a : row.b)),
    ]),
  );
  const totals = Object.fromEntries(
    providers.map((p) => [
      p,
      rows[p].reduce((sum, r) => sum + r.timings.backend_total_ms, 0),
    ]),
  );
  const largest = Math.max(totals.decider, totals.bedrock, 1);
  const differences = paired.filter(({ a, b }) => a.choice !== b.choice).length;
  return `<div class="cx-summary">
    ${providers.map((p) => `<div class="cx-speed-card ${p}"><span>${providerNames[p]} <small>决策总耗时</small></span><strong>${rows[p].length ? duration(totals[p]) : "—"}</strong><div class="cx-speed-bar"><i style="width:${(totals[p] / largest) * 100}%"></i></div><small>${rows[p].length ? `${rows[p].length} 次实测决策` : w.runMode === "replay" ? "规则回放 · 不计推理耗时" : "等待真实模型结果"}</small></div>`).join("")}
    <div class="cx-speed-ratio"><span>耗时比 <small>GPT / Decider</small></span><strong>${totals.decider > 0 && totals.bedrock > 0 ? `${(totals.bedrock / totals.decider).toFixed(1)}×` : "—"}</strong><small>${loop ? "含各自重判，调用次数可能不同" : "相同输入下的决策耗时"}</small></div>
    <div class="cx-summary-note">${w.runMode === "replay" ? `${workflowNames[w.workflowKind]} · 规则回放 · 不调用模型` : loop ? "自主闭环 · 两侧按各自执行结果继续判断" : `${workflowNames[w.workflowKind]} · 已对比 ${paired.length}/5 步 · 两侧选择不同 ${differences} 步`}<span>耗时包含模型调用与通信</span></div>
  </div>`;
}

function renderLoopHistory() {
  const w = workspace();
  if (w.workflowKind !== "loop") return "";
  return `<section class="cx-loop-history"><div class="cx-results-heading"><h2>自主闭环 · 每轮反馈与调整 · ${w.runMode === "replay" ? "规则回放" : "真实模型"}</h2><p>模型选择、实际动作和模拟器事件分别记录。最多 20 次决策，同一步连续两次无进展转人工；刷新页面会清除本次演练。</p></div><div class="cx-final-grid">${providers
    .map((provider) => {
      const e = w.executions[provider];
      return `<article class="cx-loop-lane" data-cx-loop-history="${provider}"><h3>${providerNames[provider]}</h3>${e?.timeline.length ? e.timeline.map((r, i) => `<div class="cx-loop-entry ${r.kind}"><small>第 ${i + 1} 轮 · ${r.kind === "event" ? "模拟器更新证据" : r.kind === "error" ? "请求失败" : "判断 → 执行 → 反馈"} · ${duration(r.elapsed_ms)}</small><strong>${ui.esc(r.title)}</strong><p>${ui.esc(r.reason)}</p></div>`).join("") : "<p>等待闭环运行。</p>"}</article>`;
    })
    .join("")}</div></section>`;
}

function comparisonTable() {
  const w = workspace(),
    results = w.results;
  const cell = (provider, stage) => {
    const r = results[provider][stage],
      execution = w.executions[provider];
    const record = execution?.audit.findLast((row) => row.stage === stage);
    const running = r?.pending || execution?.runningStage === stage;
    const outcome = stepOutcome(record);
    const history = (execution?.decisionHistory || []).filter(
      (d) => d.stage === stage && d.source === "live",
    );
    return `<td data-cx-compare="${provider}-${stage}"><div class="cx-table-choice">${ui.esc(r?.label || (r?.error ? "调用失败" : running ? "判断中…" : "等待运行"))}<b>${r?.source === "live" ? duration(r.timings.backend_total_ms) : r?.source === "rule_replay" ? "回放" : "—"}</b></div><div class="cx-table-action ${outcome?.state || ""}">${running ? "处理中…" : record?.error ? `请求失败：${ui.esc(record.error)}` : record?.applied ? `实际：${ui.esc(record.label)}${record.safety_adjusted ? " · 保护调整" : ""}` : r?.error ? ui.esc(r.error) : r?.choice ? "尚未执行" : "—"}</div>${history.length > 1 ? `<small>${history.length} 次判断合计 ${duration(history.reduce((n, d) => n + d.timings.backend_total_ms, 0))}</small>` : ""}</td>`;
  };
  return `<div class="cx-table-wrap"><table class="cx-compare-table"><caption>逐步流程对比${w.workflowKind === "loop" ? " · 每步最近一次结果" : ""}</caption><thead><tr><th>业务步骤</th><th>Strands Decider</th><th>GPT-6.1 Sol</th><th>选择对比</th></tr></thead><tbody>${catalog.stages
    .map((stage, i) => {
      const a = results.decider[stage.id],
        b = results.bedrock[stage.id];
      const sameInput = a?.input_hash && a.input_hash === b?.input_hash;
      const label =
        a?.choice && b?.choice
          ? sameInput
            ? a.choice === b.choice
              ? "相同"
              : "不同"
            : "不同输入"
          : "待对比";
      return `<tr><th><button data-cx-stage="${stage.id}"><span>0${i + 1}</span>${ui.esc(stage.label)}</button></th>${cell("decider", stage.id)}${cell("bedrock", stage.id)}<td><span class="cx-pair-badge ${label === "不同" ? "different" : ""}">${label}</span></td></tr>`;
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
  const live = (
    w.workflowKind === "loop"
      ? w.executions[provider]?.decisionHistory || []
      : successful
  ).filter((r) => r.source === "live");
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
      return `工单状态：${statusNames[s.ticket_status]}。客服回复（模板）：${record.customer_reply}`;
    default:
      return record.message;
  }
}

function businessOutcome(execution) {
  const s = execution?.snapshot;
  if (!s) return { fundsComplete: false, complete: false, reasons: [] };
  const records = execution.audit.filter((r) => r.applied);
  const target = {
    refund: ["refunded", "refund_payment"],
    settlement: ["settled", "reconcile_settlement"],
  }[s.scenario] || ["paid", "credit_order"];
  const fundsComplete =
    s.order_status === target[0] &&
    records.some((r) => r.ledger_entry?.type === target[1]);
  const complete =
    fundsComplete &&
    s.ticket_status === "resolved" &&
    !s.review_pending &&
    !s.risk_flag;
  const reasons = [];
  if (complete) return { fundsComplete, complete, reasons };
  if (s.risk_flag) reasons.push("存在风险标记，等待人工风控处理。");
  if (s.scenario === "settlement") {
    if (!s.settled) reasons.push("结算尚未到账，暂不能完成模拟对账。");
  } else {
    if (s.confirmations < s.required_confirmations)
      reasons.push(
        `链上确认仅 ${s.confirmations}/${s.required_confirmations}，等待确认数达标。`,
      );
    if (Number(s.received) < Number(s.expected))
      reasons.push(
        `到账仍差 ${money(Number(s.expected) - Number(s.received))} ${caseData().asset}，等待补款。`,
      );
    if (s.scenario === "refund") {
      if (!s.address_verified) reasons.push("退款地址尚未验证。");
      if (!s.approved) reasons.push("退款尚未获得人工审批。");
    }
  }
  const approval = records.findLast((r) => r.stage === "approve");
  if (s.review_pending && approval)
    reasons.push(
      `本次方案选择「${approval.label}」，待复核状态尚未解除，后续资金动作保持挂起。`,
    );
  const funds = records.findLast((r) => r.stage === "execute");
  if (!fundsComplete) {
    if (funds?.safety_adjusted)
      reasons.push(
        `原建议「${funds.requested_label}」未落实，实际改为「${funds.label}」：${funds.safety_reason}`,
      );
    else if (funds)
      reasons.push(
        `资金步骤仅采用「${funds.label}」，没有生成收款、退款或对账的模拟账本记录。`,
      );
    else reasons.push("资金步骤尚未成功处理，没有生成模拟账本记录。");
  } else if (s.ticket_status !== "resolved") {
    reasons.push("模拟资金动作已落实，客服工单尚未结案。");
  }
  return { fundsComplete, complete, reasons };
}

function stepOutcome(record) {
  if (!record?.applied) return null;
  let label,
    state = "done";
  if (record.stage === "intake") label = "已受理（模拟）";
  if (record.stage === "verify") {
    label = "已核验";
    if (
      [
        "await_confirmations",
        "request_topup",
        "settlement_delayed",
        "settlement_pending",
      ].includes(record.action)
    ) {
      label = "已核验 · 条件未满足";
      state = "pending";
    }
  }
  if (record.stage === "approve") {
    label = record.action === "approved" ? "检查通过" : record.label;
    if (record.action !== "approved") state = "pending";
  }
  if (record.stage === "execute") {
    label = record.ledger_entry
      ? "模拟资金动作已落实"
      : record.action === "escalate_settlement"
        ? "已记录升级 · 待结算"
        : record.action === "wait_settlement"
          ? "资金未执行 · 待结算"
          : "资金未执行 · 已挂起";
    if (!record.ledger_entry) state = "pending";
  }
  if (record.stage === "close") {
    label =
      record.snapshot.ticket_status === "resolved"
        ? "已回复 · 已结案"
        : "已回复 · 未结案";
    if (record.snapshot.ticket_status !== "resolved") state = "pending";
  }
  return {
    label: `${record.safety_adjusted ? "保护调整 · " : ""}${label}`,
    state,
  };
}

function finalOutcome(provider) {
  const w = workspace(),
    execution = w.executions[provider];
  const records = execution?.audit || [];
  const isLoop = execution?.kind === "loop";
  const loop = execution?.loopState;
  const completed = isLoop
    ? new Set(records.filter((r) => r.applied).map((r) => r.stage)).size
    : execution?.snapshot.completed.length || 0;
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
  const outcome = businessOutcome(execution);
  const decisions = catalog.stages.filter(
    ({ id }) => w.results[provider][id]?.choice,
  ).length;
  const interrupted =
    execution && !execution.finished && !execution.runningStage;
  let state = execution?.blocked
    ? "blocked"
    : execution?.error
      ? "error"
      : execution?.finished
        ? outcome.complete
          ? "finished"
          : "pending"
        : "waiting";
  let title = execution?.blocked
    ? "步骤未完成 · 已暂停"
    : execution?.error
      ? "执行失败 · 未完成"
      : execution?.finished
        ? outcome.complete
          ? `业务已完成（模拟）· ${statusNames[execution.snapshot.order_status]} · 已结案`
          : "业务未完成 · 持续跟进"
        : execution?.runningStage
          ? "沙盒执行中"
          : interrupted
            ? "流程已暂停"
            : "尚未执行";
  let description = execution?.blocked
    ? "后端未接受当前步骤，请刷新页面后重试。"
    : execution?.error
      ? execution.error
      : execution?.finished
        ? outcome.complete
          ? "模拟订单、对应账本记录与工单结案均已确认。"
          : outcome.fundsComplete
            ? "五个步骤均已处理，模拟资金动作已落实，但工单尚未结案。"
            : "五个步骤均已处理，收款、退款或对账动作尚未落实；5/5 不代表业务成功。"
        : interrupted
          ? "已保留完成的步骤，可继续执行剩余步骤。"
          : execution?.runningStage
            ? `正在执行「${stageData(execution.runningStage).label}」。`
            : failed
              ? "模型调用失败，尚未获得完整方案，本侧没有执行业务步骤。"
              : allDone
                ? "已生成五步建议。点击下方按钮执行，或运行上方完整流程同时查看两侧结果。"
                : "点击「开始对比」，依次生成建议并执行两套独立沙盒流程。";
  if (isLoop && !execution.error) {
    state = outcome.complete ? "finished" : "pending";
    title = outcome.complete
      ? "业务闭环已完成（模拟）· 已结案"
      : loop.status === "handoff"
        ? "闭环未完成 · 需人工处理"
        : loop.status === "waiting"
          ? "闭环等待外部条件"
          : busy
            ? "自主闭环运行中"
            : "闭环已暂停";
    description = loop.reason || "每次执行后读取实际结果，再判断下一步。";
  }
  return `<article class="cx-final-card ${provider}" data-cx-final="${provider}">
    <div class="cx-final-heading"><strong>${providerNames[provider]}</strong><span>${w.runMode === "replay" ? "规则回放 · " : ""}${isLoop ? "自主闭环 · " : ""}已处理 ${completed}/5 步</span></div>
    <div class="cx-outcome ${state}"><strong>${ui.esc(title)}</strong>${execution?.error || execution?.blocked || failed || (isLoop && loop.status === "handoff") ? `<p>${ui.esc(description)}</p>` : ""}</div>
    <div class="cx-compact-outcome"><span data-cx-funds="${outcome.fundsComplete ? "complete" : "incomplete"}">资金动作 <b>${outcome.fundsComplete ? "已落实" : "未落实"}</b></span><span>已返回 <b>${isLoop ? execution.decisionHistory.length : decisions}</b> 次决策</span></div>
    <details class="cx-result-details" data-cx-panel="outcome-${provider}" ${panelOpen(`outcome-${provider}`)}><summary>查看结果、客服回复${outcome.reasons.length ? "与未完成原因" : ""}</summary>
    ${outcome.reasons.length ? `<div class="cx-blockers"><strong>业务未完成原因</strong><ul>${outcome.reasons.map((reason) => `<li>${ui.esc(reason)}</li>`).join("")}</ul><p>${isLoop ? "闭环会携带执行反馈重判；等待外部事件或需要人工处理时暂停。" : "补齐外部证据后重新运行；若证据已满足，检查模型选择和待复核状态。固定输入流程不会自动重判。"}</p></div>` : ""}
    ${differences || adjustments ? `<p class="cx-policy-summary">参考差异 ${differences} 步 · 保护调整 ${adjustments} 步。原始模型建议均保留，参考差异不暂停流程。</p>` : ""}
    <dl class="cx-final-facts"><div><dt>订单 ${ui.esc(caseData().order_id)}</dt><dd>${execution ? ui.esc(statusNames[execution.snapshot.order_status]) : "未更新"}</dd></div><div><dt>客服工单 ${ui.esc(caseData().ticket_id)}</dt><dd>${execution ? ui.esc(statusNames[execution.snapshot.ticket_status]) : "未更新"}</dd></div><div><dt>模拟账本</dt><dd>${ledger.length ? ledger.map((r) => `${ui.esc(r.label)} · ${money(r.ledger_entry.amount)} ${ui.esc(caseData().asset)}`).join("；") : "无资金记录"}</dd></div></dl>
    <div class="cx-final-reply"><span>最终客服回复</span><p>${ui.esc(reply || "尚未执行回复结案步骤，没有发送客服回复。")}</p></div>
    ${isLoop ? `<p class="cx-loop-evidence">本侧最新证据：确认 ${execution.snapshot.confirmations}/${execution.snapshot.required_confirmations} · 到账 ${money(execution.snapshot.received)} · ${execution.snapshot.scenario === "refund" ? `地址${execution.snapshot.address_verified ? "已验证" : "未验证"} / 审批${execution.snapshot.approved ? "已通过" : "未通过"}` : execution.snapshot.scenario === "settlement" ? `结算${execution.snapshot.settled ? "已到账" : "未到账"}` : "支付核验"}</p>` : ""}
    <small class="cx-execution-time">${isLoop ? "闭环请求往返合计（含决策与模拟事件）" : "沙盒执行往返合计"}：${duration(execution?.elapsedMs)}${isLoop ? "" : " · 不计入模型推理时间"}</small>
    </details>
    ${isLoop || execution?.finished ? "" : `<div class="cx-final-actions"><button data-cx-apply="${provider}" class="secondary-button" ${busy || !allDone || execution?.finished ? "disabled" : ""}>${execution?.finished ? "本轮步骤已处理完毕" : execution ? "继续采用建议" : "采用此方案 · 模拟执行"}</button></div>`}
  </article>`;
}

function stepExecution(provider, stage) {
  const w = workspace(),
    result = w.results[provider][stage.id],
    execution = w.executions[provider];
  const records = execution?.audit.filter((r) => r.stage === stage.id) || [];
  const latest = records.at(-1);
  const outcome = stepOutcome(latest);
  const running = execution?.runningStage === stage.id;
  const state = running
    ? "running"
    : latest?.error
      ? "error"
      : latest?.applied
        ? outcome.state
        : latest
          ? "blocked"
          : "waiting";
  const status = running
    ? "执行中"
    : latest?.error
      ? "执行失败"
      : latest?.applied
        ? outcome.label
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
    <p class="cx-step-actual"><span>实际采用动作</span><b>${ui.esc(latest?.applied ? latest.label : latest?.error ? "请求失败，未确认动作" : "尚未执行")}</b></p>
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
    <div class="cx-step-timing"><span>决策：${result?.source === "live" ? duration(result.timings?.backend_total_ms) : result?.source === "rule_replay" ? "规则回放 · 未推理" : "—"}</span><span>${execution?.kind === "loop" ? `本轮往返（含决策）：${duration(latest?.tick_elapsed_ms)}` : `执行往返：${duration(latest?.elapsed_ms)}`}</span>${latest?.completed_at ? `<time datetime="${ui.esc(latest.completed_at)}">记录于 ${new Date(latest.completed_at).toLocaleTimeString("zh-CN", { hour12: false })}</time>` : ""}</div>
  </div>`;
}

function renderExecutionResults() {
  const w = workspace();
  const hasResults = providers.some(
    (p) => Object.keys(w.results[p]).length || w.executions[p],
  );
  if (!hasResults) return `<div id="cx-execution-results"></div>`;
  return `<section class="cx-execution-results" id="cx-execution-results" aria-label="逐步执行结果与最终结果">
    <div class="cx-results-heading"><h2>处理结果</h2><span>${w.runMode === "replay" ? "规则回放" : "真实模型"} · ${workflowNames[w.workflowKind]}</span></div>
    <div class="cx-final-grid">${providers.map(finalOutcome).join("")}</div>
    <div class="cx-workflow-timing"><span>${w.workflowKind === "loop" ? "本次闭环运行" : "本次流程对比"}总经过时间 <b>${duration(w.workflowElapsedMs ?? w.decisionElapsedMs)}</b></span><small>含通信与执行</small></div>
    ${w.workflowKind === "loop" ? `<details class="cx-disclosure" data-cx-panel="loop-history" ${panelOpen("loop-history")}><summary>闭环轮次与重判记录</summary>${renderLoopHistory()}</details>` : ""}
    <details class="cx-disclosure" data-cx-panel="execution" ${panelOpen("execution")}><summary>每一步的完整执行结果</summary><div class="cx-execution-steps">${catalog.stages.map((stage, i) => `<section class="cx-execution-step" aria-label="${ui.esc(stage.label)} 执行输出"><div class="cx-execution-step-heading"><h3><span>0${i + 1}</span>${ui.esc(stage.label)}</h3></div><div class="cx-step-pair">${providers.map((p) => stepExecution(p, stage)).join("")}</div></section>`).join("")}</div></details>
  </section>`;
}

function beginDialogueRun() {
  const w = workspace();
  w.dialogueRun++;
  w.viewedDialogueRun = w.dialogueRun;
}

function startDialogue(provider, number, request, kind) {
  const w = workspace();
  let turn = w.dialogues.find(
    (row) => row.run === w.dialogueRun && row.number === number,
  );
  if (!turn) {
    turn = {
      run: w.dialogueRun,
      number,
      revision: w.revision,
      kind,
      mode: w.runMode,
      sides: {},
    };
    w.dialogues.push(turn);
    w.dialogues = w.dialogues.slice(-80);
  }
  const side = {
    id: `${current}-${w.dialogueRun}-${number}-${provider}`,
    request: clone(request),
    startedAt: new Date().toISOString(),
    pending: true,
    executions: [],
  };
  turn.sides[provider] = side;
  return side;
}

function dialogueInput(side) {
  const request = side.request;
  const s = request.snapshot || request.state.snapshot;
  const stage = request.stage || request.state.next_stage;
  const feedback = request.state?.feedback || [];
  const profile = request.input_profile || "baseline";
  const modelInput = side.result?.model_input;
  return `<div class="cx-turn-input"><span class="cx-io-label">输入 · ${ui.esc(stageData(stage).label)}</span>
    <p>${ui.esc(s.message)}</p>
    <div class="cx-turn-facts"><span>应付 ${money(s.expected)} · 到账 ${money(s.received)}</span><span>确认 ${s.confirmations}/${s.required_confirmations}</span><span>${s.risk_flag ? "有风险标记" : "无风险标记"}</span>${s.scenario === "refund" ? `<span>地址${s.address_verified ? "已验证" : "未验证"} · 审批${s.approved ? "已通过" : "未通过"}</span>` : ""}${s.scenario === "settlement" ? `<span>结算${s.settled ? "已到账" : "未到账"} · ${s.settlement_minutes}/${s.settlement_sla_minutes} min</span>` : ""}</div>
    ${request.state ? `<p class="cx-turn-feedback">执行状态：${ui.esc(statusNames[s.order_status])} / ${ui.esc(statusNames[s.ticket_status])}${feedback.length ? `<br>上轮反馈：${ui.esc(feedback.at(-1).reason)}` : " · 尚无执行反馈"}</p>` : ""}
    ${profile === "optimized" ? `<p class="cx-turn-feedback" data-cx-input-profile="optimized">优化输入：${ui.esc(side.result?.input_note || catalog.optimized_profile_notes?.[s.scenario] || "按场景精简字段，明确候选适用条件。")}</p>` : ""}
    ${modelInput ? `<details class="cx-turn-raw" data-cx-panel="model-input-${side.id}" ${panelOpen(`model-input-${side.id}`)}><summary>${side.result.source === "live" ? "实际模型输入" : "回放输入结构（未调用模型）"} · 问题与候选条件</summary><pre>${ui.esc(JSON.stringify({ ...modelInput, state: JSON.parse(modelInput.state) }, null, 2))}</pre></details>` : ""}
  </div>`;
}

function dialogueOutput(provider, side, showInput) {
  if (!side)
    return `<article class="cx-turn-side ${provider}"><h4>${providerNames[provider]}</h4><p class="cx-turn-empty">本侧尚未进入此轮。</p></article>`;
  const r = side.result;
  const record = side.executions.at(-1);
  const simulation = side.response?.event;
  const pendingEvent =
    side.request.state?.status === "waiting" && side.request.auto_events;
  const time =
    r?.source === "live"
      ? `决策 ${duration(r.timings?.backend_total_ms)}`
      : r
        ? "规则回放 · 未调用模型"
        : side.pending
          ? "等待返回"
          : simulation
            ? "模拟事件 · 未调用模型"
            : side.response
              ? "流程状态 · 未调用模型"
              : "未获得模型决策";
  return `<article class="cx-turn-side ${provider}" data-cx-dialogue-output="${provider}">
    <div class="cx-turn-model"><h4>${providerNames[provider]}</h4><span>${time}</span></div>
    ${showInput ? dialogueInput(side) : ""}
    <div class="cx-turn-output"><span class="cx-io-label">${simulation ? "模拟事件输出 · 未调用模型" : r?.source === "rule_replay" ? "回放输出" : "模型输出"}</span>
      ${side.pending ? `<p class="cx-turn-pending">${pendingEvent ? "正在检查等待条件／推进模拟事件…" : "正在等待本轮决策…"}</p>` : side.error ? `<p class="cx-turn-error">请求失败：${ui.esc(side.error)}</p>` : r ? `<strong>${ui.esc(r.label)}</strong><code>${ui.esc(r.choice)}</code>` : simulation ? `<strong>${ui.esc(eventNames[simulation.name])}</strong><p>${ui.esc(eventChange(simulation.name, simulation.before, simulation.after))}</p>` : `<p>${ui.esc(side.response?.state.reason || "本轮未调用模型。")}</p>`}
    </div>
    ${record ? `<div class="cx-turn-execution"><span class="cx-io-label">实际执行${side.executions.length > 1 ? ` · 第 ${side.executions.length} 次尝试` : ""}</span><p>${ui.esc(executionOutput(record))}</p>${record.safety_reason ? `<p class="cx-turn-feedback">${ui.esc(record.safety_reason)}</p>` : ""}${record.loop_feedback ? `<p class="cx-turn-feedback">反馈：${ui.esc(record.loop_feedback.reason)}</p>` : ""}${record.customer_reply && record.stage !== "close" ? `<p class="cx-turn-reply">客服回复（模板）：${ui.esc(record.customer_reply)}</p>` : ""}</div>` : r ? `<p class="cx-turn-empty">尚未执行该建议。</p>` : ""}
    <div class="cx-turn-time"><time>${new Date(side.startedAt).toLocaleTimeString("zh-CN", { hour12: false })}</time>${side.elapsedMs != null ? `<span>请求往返 ${duration(side.elapsedMs)}</span>` : ""}</div>
    <details class="cx-turn-raw" data-cx-panel="turn-${side.id}" ${panelOpen(`turn-${side.id}`)}><summary>完整请求与返回</summary><pre>${ui.esc(JSON.stringify({ request: side.request, response: side.response || r || null, error: side.error || null, executions: side.executions }, null, 2))}</pre></details>
  </article>`;
}

function renderDialogues() {
  const w = workspace();
  const runs = [...new Set(w.dialogues.map((row) => row.run))].reverse();
  const rows = w.dialogues.filter((row) => row.run === w.viewedDialogueRun);
  return `<section class="cx-dialogues" aria-label="每轮对话输入与输出">
    <div class="cx-dialogue-heading"><h2>每轮输入 / 输出</h2><label>对比记录 <select data-cx-dialogue-run ${runs.length ? "" : "disabled"}>${runs.length ? runs.map((run) => `<option value="${run}" ${run === w.viewedDialogueRun ? "selected" : ""}>第 ${run} 次 · ${workflowNames[w.dialogues.find((row) => row.run === run).kind]}${run === w.dialogueRun ? " · 最近" : ""}</option>`).join("") : "<option>等待开始</option>"}</select></label></div>
    <div class="cx-dialogue-layout"><div class="cx-dialogue-main">
      <p class="cx-dialogue-note">${rows.length ? `${rows.length} 轮 · 滚动查看全部输入与输出` : "开始对比后逐轮显示输入与输出"} · 客服模板单独标注</p>
      <div class="cx-dialogue-feed" tabindex="0" aria-label="逐轮输入与两侧输出记录">
        ${
          rows.length
            ? rows
                .map((row) => {
                  const a = row.sides.decider,
                    b = row.sides.bedrock;
                  const sameInput =
                    a &&
                    b &&
                    JSON.stringify({
                      snapshot: a.request.snapshot || a.request.state,
                      stage: a.request.stage,
                      input_profile: a.request.input_profile,
                    }) ===
                      JSON.stringify({
                        snapshot: b.request.snapshot || b.request.state,
                        stage: b.request.stage,
                        input_profile: b.request.input_profile,
                      });
                  return `<section class="cx-turn" data-cx-dialogue-turn="${row.number}"><header><strong>第 ${row.number} 轮</strong><span>证据 v${row.revision}${row.revision < w.revision ? " · 历史输入" : ""} · ${workflowNames[row.kind]}${row.kind === "loop" ? " · 两侧各自推进" : ""} · ${row.mode === "replay" ? "规则回放" : "真实模型"}</span></header>${sameInput ? dialogueInput(a.result ? a : b) : ""}<div class="cx-turn-pair">${providers.map((p) => dialogueOutput(p, row.sides[p], !sameInput)).join("")}</div></section>`;
                })
                .join("")
            : `<div class="cx-dialogue-empty"><span class="cx-io-label">客户输入</span><p>${ui.esc(w.snapshot.message)}</p><div class="cx-turn-pair"><div><strong>Strands Decider</strong><p>等待开始对比</p></div><div><strong>GPT-6.1 Sol</strong><p>等待开始对比</p></div></div></div>`
        }
      </div>
      <small class="cx-dialogue-retention">保留最近 80 轮，可切换对比记录或导出；刷新后清除。</small>
    </div>${renderConversation()}</div>
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
    <div class="cx-card-heading"><h3>${ui.icon("message")}客户对话与回复</h3><span>${ui.esc(c.ticket_id)}</span></div>
    <div class="cx-chat-person"><span class="cx-avatar">${ui.esc(c.customer[0])}</span><div><strong>${ui.esc(c.customer)}</strong><small>订单 ${ui.esc(c.order_id)}</small></div><span class="cx-dot"></span></div>
    <div class="cx-chat" aria-label="客户诉求、模拟交易事件与客服回复记录">${history}
    ${!w.conversation.some((entry) => entry.kind === "reply") ? `<p class="cx-chat-hint">运行后显示事件与两侧回复。</p>` : ""}
    </div>
    <div class="cx-events"><strong>推进模拟交易</strong><span>${w.workflowKind === "loop" ? "更新等待中的证据，自动继续。" : "更新证据后重新开始对比。"}</span>${events.map((event) => `<button class="cx-event-button" data-cx-event="${event}" ${busy ? "disabled" : ""}>${ui.icon("plus")}${eventNames[event]}</button>`).join("")}</div>
    <label class="cx-field">修改客户诉求<textarea id="cx-message" maxlength="1800" rows="3" ${busy ? "disabled" : ""}>${ui.esc(w.snapshot.message)}</textarea></label>
    <button data-cx-save-message class="secondary-button" ${busy ? "disabled" : ""}>更新诉求并重新核验</button>
    <small class="cx-note">客服回复来自模板；模型决策见每轮输出。</small>
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
  const root = $("#crypto-workspace");
  const oldFeed = root.querySelector(".cx-dialogue-feed");
  const followLatest =
    !oldFeed ||
    oldFeed.scrollHeight - oldFeed.scrollTop - oldFeed.clientHeight < 40;
  const feedScroll = oldFeed?.scrollTop || 0;
  root.querySelectorAll("details[data-cx-panel]").forEach((el) => {
    if (el.open) expandedPanels.add(el.dataset.cxPanel);
    else expandedPanels.delete(el.dataset.cxPanel);
  });
  const c = caseData(),
    w = workspace(),
    s = w.snapshot,
    e = ui.esc;
  const disabled = busy ? "disabled" : "";
  const resumable =
    testKind === "loop" &&
    w.workflowKind === "loop" &&
    Object.values(w.executions).some(
      (x) => !["complete", "handoff"].includes(x.loopState.status),
    );
  root.innerHTML = `
    <header class="cx-comparison-title"><div><span>加密支付测试台</span><h1>Decider <small>vs</small> GPT</h1></div><div class="cx-title-actions"><button data-cx-reset class="text-button" ${disabled}>重置</button><button data-cx-export class="text-button" ${disabled}>${ui.icon("copy")}导出结果</button></div></header>
    <section class="cx-test-setup" aria-label="对比测试设置">
      <nav class="cx-scenario-tabs" aria-label="选择业务场景">${catalog.cases.map((item, i) => `<button class="cx-case ${item.id === current ? "active" : ""}" data-cx-case="${item.id}" aria-pressed="${item.id === current}" ${disabled}><small>0${i + 1}</small><strong>${e(caseNames[item.id])}</strong></button>`).join("")}</nav>
      <div class="cx-test-toolbar"><label class="cx-test-kind">测试方式<select data-cx-test-kind ${disabled}><option value="workflow" ${testKind === "workflow" ? "selected" : ""}>固定流程</option><option value="optimized" ${testKind === "optimized" ? "selected" : ""}>优化流程</option><option value="loop" ${testKind === "loop" ? "selected" : ""}>自主闭环</option></select></label><div class="mode-switch" role="group" aria-label="支付模块运行模式"><button data-cx-mode="live" class="${mode === "live" ? "active" : ""}" ${disabled}>真实模型</button><button data-cx-mode="replay" class="${mode === "replay" ? "active" : ""}" ${disabled}>规则回放</button></div><div class="cx-run-actions">${resumable ? `<button data-cx-loop-resume class="secondary-button" ${disabled}>继续本次对比</button>` : ""}<button data-cx-start class="primary-button" ${disabled}>${ui.icon("play")}${busy ? "对比中…" : "开始对比"}</button>${busy ? `<button data-cx-stop class="text-button">${stopRequested ? "正在暂停…" : "暂停"}</button>` : ""}</div></div>
      ${testKind === "optimized" ? `<p class="cx-profile-note">${e(catalog.optimized_profile_notes?.[current] || "按场景精简输入、明确候选适用条件。")} 两侧均完成五步判断与模拟执行。</p>` : ""}
      ${testKind === "loop" ? `<label class="cx-auto-events"><input type="checkbox" data-cx-auto-events ${autoEvents ? "checked" : ""} ${disabled}>自动推进模拟证据 <small>确认、补款、审批等；风险需手动解除</small></label>` : ""}
      <div class="cx-case-strip"><span>${e(c.asset)} · ${e(c.network)}</span><span>应付 <b>${money(s.expected)}</b></span><span>到账 <b>${money(s.received)}</b></span><span>${current === "settlement" ? `结算 ${s.settlement_minutes}/${s.settlement_sla_minutes} min` : `确认 ${s.confirmations}/${s.required_confirmations}`}</span><small>${w.workflowKind === "loop" ? "初始证据" : "模拟业务"}</small></div>
      <section id="cx-gpu-notice" aria-live="polite"></section>
    </section>
    <section class="cx-comparison" aria-label="Decider 与 GPT 流程速度对比">
      <div id="cx-run-status" class="cx-run-status" role="status">${busy ? `正在处理：${e(stageData(selectedStage).label)}` : ""}</div>
      ${summary()}${renderDialogues()}${comparisonTable()}${renderExecutionResults()}
    </section>
    <details class="cx-disclosure" data-cx-panel="inputs" ${panelOpen("inputs")}><summary>场景说明与证据编辑</summary><div class="cx-workspace">
      <section class="cx-card cx-order"><div class="cx-card-heading"><h2>${e(c.title)}</h2><span>证据 v${w.revision}</span></div><p class="cx-case-description">${e(c.summary)}</p><div class="cx-fact-chips"><span>${s.risk_flag ? "待人工风控" : "无风险标记"}</span>${current === "refund" ? `<span>${s.address_verified ? "地址已验证" : "地址未验证"}</span><span>${s.approved ? "审批已通过" : "待人工审批"}</span>` : ""}</div>
      <details class="cx-evidence" data-cx-panel="evidence" ${panelOpen("evidence")}><summary>编辑业务证据</summary><div class="cx-evidence-fields"><label>应付金额<input type="number" min="0.01" max="1000000" step="0.01" data-cx-field="expected" value="${e(s.expected)}" ${disabled}></label><label>实际到账<input type="number" min="0" max="1000000" step="0.01" data-cx-field="received" value="${e(s.received)}" ${disabled}></label><label>确认数<input type="number" min="0" max="1000" step="1" data-cx-field="confirmations" value="${s.confirmations}" ${disabled}></label><label>结算耗时（分钟）<input type="number" min="0" max="10080" step="1" data-cx-field="settlement_minutes" value="${s.settlement_minutes}" ${disabled}></label><label class="cx-check"><input type="checkbox" data-cx-field="risk_flag" ${s.risk_flag ? "checked" : ""} ${disabled}>风险标记</label></div></details></section></div></details>
    <details class="cx-disclosure" data-cx-panel="diagnostics" ${panelOpen("diagnostics")}><summary>决策详情与原始输出</summary><div class="cx-flow-track">${catalog.stages.map((stage, i) => `<button data-cx-stage="${stage.id}" class="${stage.id === selectedStage ? "active" : ""}"><span>${i + 1}</span><strong>${e(stage.label)}</strong></button>`).join("")}</div><div class="cx-lanes">${lane("decider")}${lane("bedrock")}</div><button data-cx-run="step" class="text-button" ${disabled}>单独对比当前步骤</button></details>
    <details class="cx-disclosure" data-cx-panel="audit" ${panelOpen("audit")}><summary>执行日志与模拟账本</summary>${renderAudit()}</details>
    <p class="cx-page-note">模拟业务，不发送资金。演练记录在刷新后清除。</p>`;
  const chat = $(".cx-chat");
  if (chat) chat.scrollTop = chat.scrollHeight;
  const feed = $(".cx-dialogue-feed");
  if (feed) feed.scrollTop = followLatest ? feed.scrollHeight : feedScroll;
  renderGpuNotice();
}

async function run(which) {
  if (busy) return;
  busy = true;
  render();
  if (!(await gpuReady())) {
    busy = false;
    render();
    return;
  }
  stopRequested = false;
  const w = workspace(),
    snapshot = clone(w.snapshot),
    runMode = mode;
  const runKind = testKind === "optimized" ? "optimized" : "fixed";
  const profileChanged = w.workflowKind !== runKind;
  w.workflowKind = runKind;
  const complete = which !== "step";
  const stages = complete ? catalog.stages.map((s) => s.id) : [selectedStage];
  if (w.runMode !== runMode || complete || profileChanged)
    w.results = { decider: {}, bedrock: {} };
  w.runMode = runMode;
  w.executions = {};
  w.activeExecution = null;
  w.decisionElapsedMs = null;
  w.workflowElapsedMs = null;
  beginDialogueRun();
  const started = performance.now();
  addAudit(
    "run",
    `${workflowNames[runKind]} · ${runMode === "live" ? "真实模型" : "规则回放"} · 开始${complete ? "五步决策" : stageData(selectedStage).label}对比，证据 v${w.revision}。`,
  );
  try {
    for (const [index, stage] of stages.entries()) {
      if (stopRequested) break;
      selectedStage = stage;
      providers.forEach((p) => {
        w.results[p][stage] = { pending: true };
      });
      render();
      await Promise.allSettled(
        providers.map(async (provider) => {
          const request = {
            snapshot,
            stage,
            provider,
            mode: runMode,
            model_id: "us.openai.gpt-6.1-sol",
            input_profile: runKind === "optimized" ? "optimized" : "baseline",
          };
          const dialogue = startDialogue(provider, index + 1, request, runKind);
          render();
          const t = performance.now();
          try {
            const result = await ui.api("/api/crypto/decision", request);
            result.client_ms =
              runMode === "live" ? performance.now() - t : null;
            w.results[provider][stage] = result;
            dialogue.result = result;
            addAudit(
              result.matches_reference ? "decision" : "warning",
              `${providerNames[provider]} · ${stageData(stage).label} → ${result.label}${result.source !== "live" ? "（规则回放）" : ""}${!result.matches_reference ? "；与演示参考不同（不因此暂停）" : ""}`,
            );
          } catch (error) {
            dialogue.error = error.message;
            w.results[provider][stage] = { error: error.message };
            addAudit(
              "error",
              `${providerNames[provider]} · ${stageData(stage).label}失败：${error.message}`,
            );
          } finally {
            dialogue.pending = false;
            dialogue.elapsedMs = performance.now() - t;
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
    if (["workflow", "optimized"].includes(which)) {
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
    if (["workflow", "optimized"].includes(which))
      $(".cx-comparison").scrollIntoView({ block: "nearest" });
  }
}

function freshLoop(snapshot) {
  return {
    kind: "loop",
    snapshot: clone(snapshot),
    audit: [],
    finished: false,
    blocked: false,
    error: null,
    runningStage: null,
    elapsedMs: 0,
    loopState: {
      snapshot: clone(snapshot),
      next_stage: "intake",
      status: "running",
    },
    decisionHistory: [],
    events: [],
    timeline: [],
    dialogueTicks: 0,
  };
}

async function runLoop(resume = false) {
  if (busy) return;
  const w = workspace();
  const runMode = resume ? w.runMode : mode;
  busy = true;
  stopRequested = false;
  render();
  if (!(await gpuReady(runMode))) {
    busy = false;
    render();
    return;
  }
  if (!resume) {
    beginDialogueRun();
    w.workflowKind = "loop";
    w.runMode = runMode;
    w.results = { decider: {}, bedrock: {} };
    w.executions = Object.fromEntries(
      providers.map((p) => [p, freshLoop(w.snapshot)]),
    );
    w.decisionElapsedMs = null;
    w.workflowElapsedMs = null;
    addAudit(
      "run",
      `${runMode === "live" ? "真实模型" : "规则回放"} · 开始自主闭环；自动模拟事件${autoEvents ? "开启" : "关闭"}。`,
    );
  }
  const started = performance.now();
  render();
  try {
    await Promise.allSettled(
      providers.map(async (provider) => {
        const execution = w.executions[provider];
        if (
          !execution ||
          ["complete", "handoff"].includes(execution.loopState.status)
        )
          return;
        execution.error = null;
        while (!stopRequested) {
          const state = execution.loopState;
          if (["complete", "handoff"].includes(state.status)) break;
          if (
            state.status === "waiting" &&
            (!autoEvents || state.waiting_events.includes("clear_risk"))
          )
            break;
          if (performance.now() - started > 300000) {
            addAudit(
              "warning",
              `${providerNames[provider]} 本次闭环运行已达到 5 分钟，自动暂停，可检查后继续。`,
            );
            break;
          }
          selectedStage = state.next_stage;
          execution.runningStage = state.next_stage;
          const request = {
            state,
            provider,
            mode: runMode,
            auto_events: autoEvents,
          };
          const dialogue = startDialogue(
            provider,
            ++execution.dialogueTicks,
            request,
            "loop",
          );
          render();
          const tickStarted = performance.now();
          try {
            const response = await ui.api("/api/crypto/loop/tick", request);
            dialogue.response = clone(response);
            dialogue.result = response.decision;
            dialogue.pending = false;
            const elapsed = performance.now() - tickStarted;
            execution.elapsedMs += elapsed;
            execution.loopState = response.state;
            execution.snapshot = clone(response.state.snapshot);
            execution.runningStage = null;
            execution.finished = response.state.status === "complete";
            if (response.decision) {
              const d = response.decision;
              w.results[provider][d.stage] = d;
              execution.decisionHistory.push(d);
            }
            if (response.record) {
              const record = {
                ...response.record,
                decision: response.decision,
                tick_elapsed_ms: elapsed,
                completed_at: new Date().toISOString(),
              };
              execution.audit.push(record);
              dialogue.executions.push(record);
              execution.timeline.push({
                kind: "decision",
                title: `${stageData(record.stage).label}：${response.decision.label} → ${record.label}`,
                reason: record.loop_feedback.reason,
                elapsed_ms: elapsed,
              });
              if (record.customer_reply)
                addConversation("reply", record.customer_reply, {
                  provider,
                  mode: runMode,
                });
              addAudit(
                record.loop_feedback.status === "succeeded"
                  ? "applied"
                  : "warning",
                `${providerNames[provider]} · 闭环第 ${response.state.decisions} 次决策：${response.decision.label} → ${record.label}。${record.loop_feedback.reason}`,
              );
            }
            if (response.event) {
              const ev = response.event;
              execution.events.push(ev);
              const change = eventChange(ev.name, ev.before, ev.after);
              execution.timeline.push({
                kind: "event",
                title: `模拟器：${eventNames[ev.name]}`,
                reason: `${change}。${ev.message}`,
                elapsed_ms: elapsed,
              });
              addConversation(
                "event",
                `${providerNames[provider]} · 模拟器更新：${change}。这是模拟证据，闭环将自动继续判断。`,
                { event: ev.name, provider, source: "simulator" },
              );
              addAudit(
                "event",
                `${providerNames[provider]} · 模拟器：${change}。`,
              );
            }
            render();
          } catch (error) {
            dialogue.error = error.message;
            dialogue.pending = false;
            const elapsed = performance.now() - tickStarted;
            execution.elapsedMs += elapsed;
            execution.error = error.message;
            execution.runningStage = null;
            execution.audit.push({
              stage: state.next_stage,
              error: error.message,
              tick_elapsed_ms: elapsed,
              completed_at: new Date().toISOString(),
            });
            execution.timeline.push({
              kind: "error",
              title: `${stageData(state.next_stage).label}：本轮请求失败`,
              reason: error.message,
              elapsed_ms: elapsed,
            });
            w.results[provider][state.next_stage] = { error: error.message };
            addAudit(
              "error",
              `${providerNames[provider]} 闭环已暂停：${error.message}`,
            );
            render();
            break;
          } finally {
            dialogue.elapsedMs = performance.now() - tickStarted;
          }
        }
      }),
    );
  } finally {
    w.workflowElapsedMs = performance.now() - started;
    busy = false;
    stopRequested = false;
    render();
    $(".cx-comparison")?.scrollIntoView({ block: "nearest" });
  }
}

async function applyLoopEvent(name) {
  const w = workspace();
  const targets = providers.filter((p) => {
    const e = w.executions[p];
    return (
      e?.loopState.status === "waiting" &&
      e.loopState.waiting_events.includes(name)
    );
  });
  if (!targets.length) {
    ui.toast("当前闭环没有等待此事件；需要重新演练时请重置案例。");
    return;
  }
  busy = true;
  render();
  let changed = false;
  try {
    for (const provider of targets) {
      const e = w.executions[provider],
        before = clone(e.snapshot);
      const result = await ui.api("/api/crypto/event", {
        snapshot: before,
        event: name,
      });
      const s = result.snapshot;
      s.completed = before.completed.filter((stage) => stage === "intake");
      e.snapshot = s;
      Object.assign(e.loopState, {
        snapshot: clone(s),
        next_stage: s.completed.includes("intake") ? "verify" : "intake",
        status: "running",
        no_progress: 0,
        waiting_events: [],
        reason: "已收到手动模拟事件，将按最新证据重新判断。",
        feedback: [
          ...e.loopState.feedback,
          {
            stage: "event",
            status: "simulated_event",
            requested_action: "",
            actual_action: name,
            reason: `User advanced sandbox event ${name}. Recheck the latest verified facts.`,
          },
        ].slice(-8),
      });
      const change = eventChange(name, before, s);
      e.events.push({
        name,
        before,
        after: clone(s),
        source: "manual_simulator",
      });
      e.timeline.push({
        kind: "event",
        title: `手动模拟事件：${eventNames[name]}`,
        reason: change,
        elapsed_ms: null,
      });
      addConversation(
        "event",
        `${providerNames[provider]} · 手动推进模拟事件：${change}。保留历史，闭环将继续。`,
        { event: name, provider, source: "manual_simulator" },
      );
      changed = true;
    }
  } catch (error) {
    ui.toast(error.message);
    addAudit("error", `模拟事件未完成：${error.message}`);
  } finally {
    busy = false;
    render();
  }
  if (changed) await runLoop(true);
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
      const dialogue = w.dialogues.findLast(
        (row) => row.sides[provider]?.result === result,
      )?.sides[provider];
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
        const failed = {
          stage: stage.id,
          action: choice,
          label: catalog.options[stage.id][choice],
          error: error.message,
          elapsed_ms: elapsed,
          completed_at: new Date().toISOString(),
        };
        execution.audit.push(failed);
        dialogue?.executions.push(failed);
        throw error;
      }
      const elapsed = performance.now() - started;
      execution.elapsedMs += elapsed;
      const record = {
        stage: stage.id,
        elapsed_ms: elapsed,
        completed_at: new Date().toISOString(),
        ...applied,
      };
      execution.audit.push(record);
      dialogue?.executions.push(record);
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
        businessOutcome(execution).complete ? "applied" : "warning",
        `${providerNames[provider]} 本轮五步已处理；${businessOutcome(execution).complete ? "业务已完成（模拟）" : "业务未完成"}：${statusNames[execution.snapshot.ticket_status]} / ${statusNames[execution.snapshot.order_status]}。`,
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
  if (button.hasAttribute("data-cx-gpu-open")) {
    ui.openGpuDialog();
    return;
  }
  if (button.hasAttribute("data-cx-stop")) {
    stopRequested = true;
    button.textContent = "当前步骤后停止…";
    return;
  }
  if (button.dataset.cxStage) {
    if (!busy) {
      selectedStage = button.dataset.cxStage;
      render();
      $('[data-cx-panel="diagnostics"]').open = true;
    }
    return;
  }
  if (busy) return;
  if (button.hasAttribute("data-cx-start")) {
    if (testKind === "loop") await runLoop();
    else await run(testKind);
    return;
  }
  if (button.hasAttribute("data-cx-loop-resume")) {
    await runLoop(true);
    return;
  }
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
    if (workspace().workflowKind === "loop") {
      await applyLoopEvent(simulationEvent);
      return;
    }
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
            businessOutcomes: Object.fromEntries(
              providers.map((provider) => [
                provider,
                businessOutcome(workspace().executions[provider]),
              ]),
            ),
            note: "模拟业务流程；已处理步骤数不等于业务完成，参考一致率不是通用准确率。未执行真实资金操作。",
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
  if (event.target.hasAttribute("data-cx-dialogue-run")) {
    workspace().viewedDialogueRun = Number(event.target.value);
    render();
    const feed = $(".cx-dialogue-feed");
    if (feed) feed.scrollTop = 0;
    return;
  }
  if (event.target.hasAttribute("data-cx-test-kind") && !busy) {
    testKind = event.target.value;
    render();
    return;
  }
  if (event.target.hasAttribute("data-cx-auto-events") && !busy) {
    autoEvents = event.target.checked;
    return;
  }
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
