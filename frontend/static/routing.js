let ui,
  catalog,
  loading = false,
  loaded = false,
  busy = false,
  executing = "",
  stopped = false;
let current = "support",
  mode = "live",
  filter = "",
  sequence = 0;
const workspaces = new Map();
const providers = ["decider", "jev", "bedrock"];
const names = {
  decider: "Strands Decider",
  jev: "Jev",
  bedrock: "GPT-6 Sol · low",
};
const $ = (s) => document.querySelector(s);
const ms = (n) =>
  n == null
    ? "—"
    : n >= 1000
      ? `${(n / 1000).toFixed(2)} s`
      : `${n.toFixed(1)} ms`;
const num = (n, digits = 2) => (n == null ? "—" : n.toFixed(digits));
const escape = (s) => ui.esc(String(s ?? ""));
const workspace = () => workspaces.get(current);
const emptySides = () =>
  Object.fromEntries(
    providers.map((p) => [p, { steps: [], error: null, execution: null }]),
  );
const resultOf = (side) => side.steps.find((r) => r.stage === "model");
const flowOf = (side) => side.steps.find((r) => r.stage === "workflow");
const stages = { workflow: "选择处理流程", model: "选择目标模型" };
const selected = (side) => resultOf(side)?.selected_model;
const total = (side) =>
  side.steps.some((r) => r.source === "live")
    ? side.steps.reduce((n, r) => n + (r.timings?.backend_total_ms || 0), 0)
    : null;
const newWorkspace = (c) => ({
  task: { text: c.task, allow_cross_region: true, include_legacy: false },
  sides: emptySides(),
  runStrategy: null,
  elapsed: null,
  runMode: null,
  candidates: null,
  runTask: null,
});
const canExecute = (r) =>
  r?.selected_model &&
  [
    "customer_support",
    "coding",
    "reasoning",
    "general_text",
    "embedding",
  ].includes(r.workflow.id);

export async function mountRouting(helpers) {
  ui = helpers;
  if (loaded || loading) return;
  loading = true;
  try {
    catalog = await ui.api("/api/routing/catalog");
    catalog.cases.forEach((c) => workspaces.set(c.id, newWorkspace(c)));
    const root = $("#routing-workspace");
    root.addEventListener("click", click);
    root.addEventListener("change", change);
    root.addEventListener("input", (event) => {
      if (event.target.matches("[data-rt-search]")) {
        filter = event.target.value;
        renderCatalog();
      }
    });
    loaded = true;
    render();
    await updateCandidates();
  } catch (e) {
    $("#routing-workspace").innerHTML =
      `<div class="result-error">模型路由加载失败：${escape(e.message)} <button data-rt-reload>重新加载</button></div>`;
    $("[data-rt-reload]").onclick = () => mountRouting(helpers);
  } finally {
    loading = false;
  }
}

async function updateCandidates() {
  const w = workspace(),
    revision = ++sequence;
  try {
    const result = await ui.api("/api/routing/candidates", w.task);
    if (revision !== sequence) return;
    w.candidates = result;
    renderCatalog();
  } catch (e) {
    ui.toast(e.message);
  }
}

function render() {
  const w = workspace(),
    ranks = catalog.rankings;
  $("#routing-workspace").innerHTML = `
    <div class="rt-heading"><div><span class="tiny-label">TASK → WORKFLOW → MODEL</span><h1>模型路由对比</h1>
    <p>Strands Decider vs Jev vs GPT-6 Sol <span class="rt-chip">low effort</span></p></div>
    <button class="text-button" data-rt-catalog>${escape(catalog.region)} · ${catalog.models.length} 个模型</button></div>
    <div class="rt-cases">${catalog.cases.map((c) => `<button class="rt-case ${current === c.id ? "active" : ""}" data-rt-case="${c.id}" ${busy ? "disabled" : ""}><strong>${escape(c.title)}</strong><span>${escape(c.description)}</span></button>`).join("")}</div>
    <section class="rt-input"><label for="rt-task">任务输入</label>
      <textarea id="rt-task" maxlength="1400" rows="3" ${busy ? "disabled" : ""}>${escape(w.task.text)}</textarea>
      <details><summary>区域与版本限制</summary><div class="rt-fields">
      <label class="rt-check"><input type="checkbox" data-rt-field="allow_cross_region" ${w.task.allow_cross_region ? "checked" : ""} ${busy ? "disabled" : ""}>允许跨区域推理配置</label>
      <label class="rt-check"><input type="checkbox" data-rt-field="include_legacy" ${w.task.include_legacy ? "checked" : ""} ${busy ? "disabled" : ""}>纳入旧版模型</label></div></details>
    </section>
    <div class="rt-controls">
      <button class="primary-button" data-rt-start ${busy ? "disabled" : ""}>${busy ? escape(executing || "正在对比…") : "开始路由对比"}</button>
      <button class="secondary-button" data-rt-all ${busy ? "disabled" : ""}>测试全部 4 场景</button>
      <label>运行方式<select data-rt-mode ${busy ? "disabled" : ""}><option value="live" ${mode === "live" ? "selected" : ""}>真实三模型对比</option><option value="replay" ${mode === "replay" ? "selected" : ""}>界面回放 · 不调用模型</option></select></label>
      ${busy ? '<button class="secondary-button" data-rt-stop>完成本场景后停止</button>' : ""}
      <button class="text-button" data-rt-export>导出结果</button>
    </div>
    <p class="rt-source">评测来源：<a href="${escape(ranks.profile.url)}" target="_blank" rel="noopener">${escape(ranks.profile.name)}</a> · <a href="${escape(ranks.embedding_source.url)}" target="_blank" rel="noopener">MTEB</a>
      <span>快照 ${escape(ranks.captured_at.slice(0, 10))} · ${Object.keys(ranks.entries).length} 个型号有映射</span></p>
    <div id="rt-results" aria-live="polite"></div>
    <details class="rt-overview"><summary>评测来源与候选范围</summary>
      <p>${escape(ranks.profile.note)} ${escape(ranks.embedding_source.note)}</p>
      <p>原始流程：模型选流程 → 模型选型号。三路分别由 Strands Decider、Jev、GPT 完成两次判断。</p>
      <p>候选按账户、区域、模态与评测映射筛选，再由模型选择；同一流程使用相同候选与顺序，任务输入不添加优先级。</p>
      <p>${ranks.profile.speed_available ? "第三方速度仅作参考，不能代表 Bedrock 实测。" : "当前 LiveBench 快照不含速度指标，不宣称目标模型最快。"} 两步决策与目标执行分别计时。</p>
      <p>Artificial Analysis：${ranks.profile.id === "artificial_analysis" ? "已接入官方 API 快照。" : "尚未配置 API key；当前使用 LiveBench。"} <a href="https://artificialanalysis.ai/documentation" target="_blank" rel="noopener">API 文档</a></p>
    </details>
    <details id="rt-catalog" class="rt-catalog"><summary>Bedrock 完整模型目录 · ${catalog.models.length} 个</summary>
      <p>采集时间：${escape(catalog.captured_at)} · 未排名的模型仍保留在目录中。</p>
      <input data-rt-search placeholder="搜索模型、提供商或模态" value="${escape(filter)}" aria-label="搜索模型目录">
      <div id="rt-catalog-table"></div>
    </details>`;
  renderResults();
  renderCatalog();
}

function evidenceDetail(r) {
  if (!r) return "";
  const pool = r.selection,
    benchmark = pool.selected_benchmark,
    m = benchmark.metrics;
  return `<div class="rt-ranking"><strong>所选型号的第三方评测</strong>
    <p>${m.quality != null ? `综合 ${num(m.quality)} · 代码 ${num(m.coding)}` : `检索 ${num(m.retrieval)}`}
    ${m.input_price != null ? `<br>参考 USD / 百万 token：输入 ${num(m.input_price, 3)} · 输出 ${num(m.output_price, 3)}` : ""}</p>
    <small>${escape(benchmark.benchmark_configuration)}</small>
    <details><summary>候选池与基准快照 · ${pool.candidate_count} 个型号</summary>
      <p>满足调用条件 ${pool.available_model_count} 个；有评测映射 ${pool.candidate_count} 个。按模型 ID 排列，不是推荐顺序。实际发送的指标见对应路径的输入输出。</p>
      <div class="rt-scroll"><table><thead><tr><th>候选</th><th>综合</th><th>代码</th><th>检索</th></tr></thead><tbody>${pool.candidates.map((row) => `<tr><td>${escape(row.candidate_id)} · ${escape(row.model.name)}${row.candidate_id === r.choice ? " ✓" : ""}</td><td>${num(row.benchmark.metrics.quality)}</td><td>${num(row.benchmark.metrics.coding)}</td><td>${num(row.benchmark.metrics.retrieval)}</td></tr>`).join("")}</tbody></table></div>
      <a href="${escape(benchmark.source_url)}" target="_blank" rel="noopener">评测来源</a>
      <details><summary>未纳入候选的原因</summary><pre>${escape(JSON.stringify(pool.excluded, null, 2))}</pre></details>
    </details></div>`;
}

function executionDetail(side) {
  const x = side.execution;
  if (!x) return "";
  return `<div class="rt-execution"><strong>${x.error ? "执行失败" : x.complete ? "目标模型返回结果" : "未生成完整结果"}</strong>
    <span>${x.error ? `请求等待 ${ms(x.client_total_ms)}` : `目标执行 ${ms(x.backend_total_ms)}`}</span>
    <pre>${escape(x.error || x.text)}</pre>${x.vector_preview ? `<pre>${escape(JSON.stringify(x.vector_preview))}</pre>` : ""}
    <small>${escape(JSON.stringify(x.usage || {}))}</small></div>`;
}

function sideCard(side, provider, w) {
  const flow = flowOf(side),
    r = resultOf(side),
    model = selected(side);
  return `<article class="rt-side ${provider}" data-rt-side="${provider}">
    <div class="rt-model-name">${names[provider]}</div>
    <strong class="rt-time">${ms(total(side))}</strong><span class="rt-muted">${w.runMode === "replay" ? "回放 · 未调用模型" : `${side.steps.filter((x) => x.source === "live").length} 次已返回决策合计`}</span>
    <h3>① ${flow ? escape(flow.label) : "等待流程选择"}</h3>
    ${flow ? `<p class="rt-workflow-plan">${flow.workflow.steps.map(escape).join(" → ")}</p><small>流程选择 ${ms(flow.timings?.backend_total_ms)}</small>` : ""}
    <div class="rt-selection"><span>② ${names[provider]} 选择的型号</span>
      <h3>${model ? escape(model.name) : side.error ? "未完成" : r ? "未选出型号" : "等待选择"}</h3>
      ${model ? `<code>${escape(model.id)}</code><p>型号选择 ${ms(r.timings?.backend_total_ms)}</p>` : ""}</div>
    ${evidenceDetail(r)}
    ${side.error ? `<div class="rt-error">${escape(side.error)}</div>` : ""}
    ${canExecute(r) && w.runMode === "live" ? `<button class="secondary-button" data-rt-execute="${provider}" ${busy ? "disabled" : ""}>执行目标模型</button>` : ""}
    ${executionDetail(side)}</article>`;
}

function renderResults() {
  const w = workspace();
  const completed = providers.filter((p) => selected(w.sides[p])).length;
  $("#rt-results").innerHTML = `
    <div class="rt-result-heading"><h2>流程、模型选择与速度</h2><span>${w.runMode === "replay" ? "界面回放 · 无模型推理" : `完成 ${completed}/3 条路由 · 整轮 ${ms(w.elapsed)}`}</span>
    ${w.runMode === "live" && completed ? `<button class="secondary-button" data-rt-execute-all ${busy ? "disabled" : ""}>执行三侧目标模型</button>` : ""}</div>
    <h3 class="rt-variant-title">原始流程：模型选流程 → 模型选型号</h3>
    <div class="rt-sides">${providers.map((p) => sideCard(w.sides[p], p, w)).join("")}</div>
    <p class="rt-note">流程为处理计划，执行后才调用目标模型；不会自动运行代码测试或搜索知识库。</p>
    ${Object.entries(stages)
      .map(([stage, label], index) => {
        const rows = providers.map((p) =>
          w.sides[p].steps.find((r) => r.stage === stage),
        );
        if (!rows.some(Boolean)) return "";
        const identical =
          rows.every(Boolean) &&
          new Set(rows.map((r) => r.input_hash)).size === 1;
        return `<section class="rt-round" data-rt-stage="${stage}"><div class="rt-round-title"><h3>${index + 1}. ${label} · 输入与输出</h3><span>${identical ? "三侧输入相同" : "沿各自所选流程继续"}</span></div>
        <div class="rt-turn-input"><b>原始任务</b><p>${escape(w.runTask.text)}</p></div>
        <div class="rt-sides">${providers
          .map((p, i) => {
            const r = rows[i];
            return `<div class="rt-turn-output"><b>${names[p]}</b>${r ? `<h4>${escape(r.label)}</h4><code>${escape(JSON.stringify({ choice: r.choice }))}</code><p>${r.candidate_count} 个候选 · ${ms(r.timings?.backend_total_ms)}${r.notice ? " · " + escape(r.notice) : ""}</p><details><summary>实际输入 / 输出 / token</summary><pre>${escape(JSON.stringify({ input: r.model_input || r.policy_input, source: r.source, output: { model: r.model, choice: r.choice, probabilities: r.probabilities, confidence: r.confidence, usage: r.usage, timings: r.timings }, input_hash: r.input_hash }, null, 2))}</pre></details>` : "<p>未返回有效结果。</p>"}</div>`;
          })
          .join("")}</div></section>`;
      })
      .join("")}
    <details class="rt-overview"><summary>四场景汇总</summary><div class="rt-scroll"><table><thead><tr><th>场景</th>${providers.map((p) => `<th>${names[p]}</th>`).join("")}</tr></thead><tbody>
    ${catalog.cases
      .map((c) => {
        const item = workspaces.get(c.id);
        return `<tr><th>${escape(c.title)}</th>${providers.map((p) => `<td>${escape(selected(item.sides[p])?.name || "—")} · ${ms(total(item.sides[p]))}</td>`).join("")}</tr>`;
      })
      .join("")}</tbody></table></div></details>`;
}

function renderCatalog() {
  const el = $("#rt-catalog-table");
  if (!el) return;
  const w = workspace(),
    q = filter.toLowerCase();
  const rows = catalog.models.filter((m) =>
    JSON.stringify([
      m.id,
      m.name,
      m.provider,
      m.input_modalities,
      m.output_modalities,
    ])
      .toLowerCase()
      .includes(q),
  );
  const available = new Set(w.candidates?.eligible || []);
  el.innerHTML = `<p>基础调用条件通过 ${w.candidates ? available.size : "…"} / ${catalog.models.length} 个 · 展示 ${rows.length} 个</p>
    <div class="rt-scroll"><table><thead><tr><th>模型 / 提供商</th><th>输入 → 输出</th><th>调用方式</th><th>评测映射 / 可用性</th></tr></thead><tbody>${rows
      .map((m) => {
        const ranking = catalog.rankings.entries[m.id];
        return `<tr><td><strong>${escape(m.name)}</strong><small>${escape(m.provider)} · ${escape(m.id)}</small></td><td>${escape(m.input_modalities.join(", "))} → ${escape(m.output_modalities.join(", "))}</td><td>${m.invocation === "regional" ? "本区域" : m.invocation === "inference_profile" ? "推理配置" : "需预置容量"}<small>${escape(m.destination_regions.join(", "))}</small></td><td>${ranking ? escape(ranking.source) + " · 已映射" : "未排名"}<small>${available.has(m.id) ? "基础条件通过；流程选择后按模态筛选" : escape(w.candidates?.excluded[m.id] || "正在检查")}</small></td></tr>`;
      })
      .join(
        "",
      )}</tbody></table></div><p class="rt-note">目录包含容量变体；不把相似名称视为同一模型。账户状态以采集时为准，运行时权限与配额以实际调用为准。</p>`;
}

async function runOne() {
  const w = workspace();
  w.sides = emptySides();
  w.runMode = mode;
  w.runStrategy = "original";
  w.runTask = structuredClone(w.task);
  w.elapsed = null;
  const start = performance.now();
  const versions = {
    catalog_version: catalog.version,
    ranking_version: catalog.rankings.version,
  };
  await Promise.all(
    providers.map(async (provider) => {
      const side = w.sides[provider];
      let flow;
      try {
        flow = await ui.api("/api/routing/decision", {
          task: w.runTask,
          provider,
          mode: w.runMode,
          stage: "workflow",
          strategy: "original",
          ...versions,
        });
        side.steps.push(flow);
      } catch (e) {
        side.error = `流程判断：${e.message}`;
        renderResults();
        return;
      }
      renderResults();
      try {
        side.steps.push(
          await ui.api("/api/routing/decision", {
            task: w.runTask,
            provider,
            mode: w.runMode,
            stage: "model",
            workflow: flow.choice,
            strategy: "original",
            ...versions,
          }),
        );
      } catch (e) {
        side.error = `型号判断：${e.message}`;
      }
      renderResults();
    }),
  );
  w.elapsed = performance.now() - start;
  renderResults();
}

async function run(all) {
  if (busy) return;
  if (!workspace().task.text.trim()) {
    ui.toast("请输入任务。");
    return;
  }
  if (mode === "live" && !(await ui.ensureGpuReady("模型路由对比"))) return;
  busy = true;
  stopped = false;
  render();
  try {
    for (const id of all ? catalog.cases.map((c) => c.id) : [current]) {
      if (stopped) break;
      current = id;
      render();
      await updateCandidates();
      await runOne();
    }
  } finally {
    busy = false;
    render();
  }
}

async function executeOne(provider) {
  const w = workspace(),
    side = w.sides[provider],
    r = resultOf(side);
  if (!canExecute(r) || w.runMode !== "live") return;
  executing = `执行 ${names[provider]} 的目标模型…`;
  render();
  const started = performance.now();
  try {
    side.execution = await ui.api("/api/routing/execute", {
      task: w.runTask,
      workflow: r.workflow.id,
      model_id: r.selected_model.id,
      catalog_version: catalog.version,
      ranking_version: catalog.rankings.version,
      strategy: "original",
    });
  } catch (e) {
    side.execution = { error: e.message, status: e.status };
  }
  side.execution.client_total_ms = performance.now() - started;
  renderResults();
}

async function execute(provider, all = false) {
  if (busy) return;
  busy = true;
  render();
  try {
    if (!all) await executeOne(provider);
    else for (const p of providers) await executeOne(p);
  } finally {
    busy = false;
    executing = "";
    render();
  }
}

function click(event) {
  const el = event.target.closest("button");
  if (!el) return;
  if (el.hasAttribute("data-rt-start")) return run(false);
  if (el.hasAttribute("data-rt-all")) return run(true);
  if (el.hasAttribute("data-rt-stop")) {
    stopped = true;
    el.textContent = "本场景结束后停止";
    return;
  }
  if (el.hasAttribute("data-rt-catalog")) {
    $("#rt-catalog").open = true;
    $("#rt-catalog").scrollIntoView({ behavior: "smooth" });
    return;
  }
  if (el.hasAttribute("data-rt-case") && !busy) {
    current = el.dataset.rtCase;
    render();
    updateCandidates();
  }
  if (el.hasAttribute("data-rt-execute"))
    return execute(el.dataset.rtExecute);
  if (el.hasAttribute("data-rt-execute-all")) return execute(null, true);
  if (el.hasAttribute("data-rt-export")) {
    const data = {
      exported_at: new Date().toISOString(),
      catalog_version: catalog.version,
      catalog_region: catalog.region,
      ranking_version: catalog.rankings.version,
      ranking_source: catalog.rankings.profile,
      routing_version: catalog.routing_version,
      strategy: "original",
      comparison_method:
        "Each provider independently selects a workflow, then a target model using original evidence. The same workflow uses identical candidate IDs and order. Target executions are separate calls.",
      router_model: catalog.router_model,
      reasoning_effort: "low",
      cases: Object.fromEntries(workspaces),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `ranked-model-routing-${Date.now()}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function change(event) {
  if (busy) return;
  const el = event.target,
    w = workspace();
  if (el.hasAttribute("data-rt-mode")) {
    mode = el.value;
    render();
    return;
  }
  if (el.id === "rt-task") w.task.text = el.value;
  else if (el.dataset.rtField) w.task[el.dataset.rtField] = el.checked;
  else return;
  w.sides = emptySides();
  w.runStrategy = null;
  w.elapsed = null;
  w.runTask = null;
  w.runMode = null;
  w.candidates = null;
  renderResults();
  updateCandidates();
}
