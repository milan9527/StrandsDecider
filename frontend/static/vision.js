let ui, catalog, root, loaded = false, loading = false, busy = false;
let group = "payment", caseId = "case-01", variant = "original";
let uploaded = null, outcomes = {}, error = "", connected = null, revision = 0, runMode = "recorded";
let totalMs = null;
const providers = [
  {id: "decider", name: "Strands Decider", detail: "v19 · 官方视觉服务"},
  {id: "jev", name: "Jev", detail: "System One · 图片输入"},
  {id: "bedrock", name: "GPT-6.1 Sol", detail: "Bedrock · low effort"},
];
const ms = (value) => value == null ? "—" : value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(1)} ms`;
const labels = {
  completed: "支付成功", pending: "等待确认", failed: "付款失败", unknown: "信息不足",
  confirm: "告知付款已完成", wait: "继续等待", retry: "检查原因后重试", review: "补充清晰截图",
  refunds: "退款队列", payment_issues: "支付故障队列", account_access: "账号访问队列",
  product_information: "产品咨询队列", accept: "接收凭证", request_signature: "要求补签",
  request_reference: "要求补交易编号", request_both: "补全编号和签名",
};
const questionNames = {
  status: "付款状态", next_action: "下一步动作", paid: "是否已支付成功",
  queue: "客服队列", signature: "是否存在签名", reference: "是否有交易编号", action: "凭证处理动作",
};
const variants = {original: "原始候选", reverse: "反转候选顺序", no_image: "不发送图片", blank: "替换为白图"};
const esc = (value) => ui.esc(value);
const selectedCase = () => catalog.cases.find((c) => c.id === caseId);
const chosenLabel = (value) => typeof value === "boolean" ? (value ? "是" : "否") : labels[value] || value;
const lock = () => busy ? "disabled" : "";
const answerValue = (a) => a.type === "choice" ? a.choice : typeof a.value === "boolean" ? a.value : a.noul >= .5;

export async function mountVision(helpers) {
  ui = helpers;
  if (loaded || loading) return;
  loading = true;
  root = document.querySelector("#vision-workspace");
  try {
    catalog = await ui.api("/api/vision/catalog");
    root.addEventListener("click", click);
    root.addEventListener("change", change);
    loaded = true;
    render();
    refreshHealth();
    await run("recorded");
  } catch (e) {
    root.innerHTML = `<div class="result-error">图片决策加载失败：${esc(e.message)} <button data-v-reload>重新加载</button></div>`;
    root.querySelector("[data-v-reload]").onclick = () => mountVision(helpers);
  } finally {
    loading = false;
  }
}

async function refreshHealth() {
  try {
    connected = (await ui.api("/api/vision/health")).connected;
  } catch {
    connected = false;
  }
  const badge = root.querySelector("[data-v-health]");
  if (badge) {
    badge.textContent = connected ? "Decider 视觉服务就绪" : "Decider 视觉服务暂不可用";
    badge.classList.toggle("ready", connected);
  }
}

function render() {
  const c = selectedCase();
  const source = variant === "blank" ? "/static/vision/blank.png" : uploaded?.url || c?.image_url;
  const questions = structuredClone(c?.questions || catalog.groups.find((g) => g.id === group).questions);
  if (variant === "reverse") for (const q of Object.values(questions)) {
    if (q.type === "choice") q.criteria = Object.fromEntries(Object.entries(q.criteria).reverse());
  }
  root.innerHTML = `
    <div class="vs-heading"><div><span class="tiny-label">STRANDS DECIDER · VISION</span><h1>图片决策</h1>
      <p>同一图片、同一问题，比较三个模型的选择与速度。</p></div>
      <button class="vs-health ${connected ? "ready" : ""}" data-v-health>${connected === null ? "检查 Decider…" : connected ? "Decider 视觉服务就绪" : "Decider 视觉服务暂不可用"}</button>
    </div>
    <div class="vs-tabs" role="group" aria-label="图片决策场景">${catalog.groups.map((g) =>
      `<button data-v-group="${g.id}" aria-pressed="${group === g.id}" class="${group === g.id ? "active" : ""}" ${lock()}>${esc(g.title)}</button>`).join("")}</div>
    <div class="vs-controls">
      <button class="primary-button" data-v-run ${lock()}>${ui.icon("play")}${busy ? "三个模型正在判断…" : "开始三模型对比"}</button>
      <button class="secondary-button" data-v-recorded ${lock()} ${uploaded ? "disabled" : ""}>Decider 历史实测</button>
      <label>对照方式<select data-v-variant ${lock()}>${Object.entries(variants).map(([id, text]) =>
        `<option value="${id}" ${id === variant ? "selected" : ""}>${text}</option>`).join("")}</select></label>
      <button class="text-button" data-v-export ${!Object.keys(outcomes).length || busy ? "disabled" : ""}>导出对比</button>
    </div>
    ${error ? `<div class="vs-error" role="alert">${esc(error)}</div>` : ""}
    <section class="vs-input-grid">
      <div class="vs-image-panel"><div class="vs-panel-heading"><h2>输入图片</h2><span>${uploaded ? "自行上传" : "合成测试截图"}</span></div>
        <label class="vs-select-label">预设图片<select data-v-case ${lock()}>
          ${uploaded ? '<option value="" selected>当前上传图片</option>' : ""}
          ${catalog.cases.filter((item) => item.group === group).map((item) =>
            `<option value="${item.id}" ${item.id === caseId ? "selected" : ""}>${esc(item.title)}</option>`).join("")}
        </select></label>
        <div class="vs-image-wrap ${variant === "no_image" ? "omitted" : ""}">
          <img src="${esc(source)}" alt="${esc(uploaded?.name || c?.title || "待判断图片")}">
          ${variant === "no_image" ? '<div class="vs-image-overlay">本次请求不发送图片</div>' : ""}
          <button class="vs-image-zoom" data-v-zoom>放大图片</button>
        </div>
        <label class="secondary-button vs-upload">${ui.icon("plus")}上传图片<input type="file" data-v-upload accept="image/png,image/jpeg,image/webp" ${lock()}></label>
        <p class="vs-hint">${uploaded ? `${esc(uploaded.name)} · 三模型共用 ${uploaded.width} × ${uploaded.height} PNG` : "上传统一为 448 × 448 PNG，保留比例并补白"}</p>
      </div>
      <div class="vs-shared-input"><div class="vs-panel-heading"><h2>三个模型收到的问题</h2><span>${Object.keys(questions).length} 项独立判断</span></div>
        <p class="vs-hint">请根据所附截图中的可见内容回答问题。</p>
        <div class="vs-question-list">${Object.entries(questions).sort(([a],[b]) => Number(b === "action") - Number(a === "action")).map(([id,q]) =>
          `<article class="vs-question-preview"><strong>${esc(questionNames[id])}</strong><p>${esc(q.instructions)}</p>
          ${q.type === "choice" ? `<details><summary>查看 ${Object.keys(q.criteria).length} 个相同候选</summary><dl>${Object.entries(q.criteria).map(([key,value]) =>
            `<dt>${esc(labels[key] || key)} <code>${esc(key)}</code></dt><dd>${esc(value)}</dd>`).join("")}</dl></details>` : '<span class="vs-hint">返回是／否判断</span>'}</article>`).join("")}</div>
      </div>
    </section>
    <div class="vs-comparison-summary" data-v-summary>${comparisonSummary()}</div>
    <section class="vs-result-grid" aria-live="polite" aria-busy="${busy}">
      ${providers.map((provider) => modelCard(provider)).join("")}
    </section>
    <details class="vs-notes"><summary>查看测试口径与模型信息</summary>
      <p>Decider 使用官方视觉服务；Jev 使用支持图片的 System One 接口；GPT 使用 Bedrock Converse。三个模型直接读取相同图片，没有先 OCR。Jev 官方图片功能目前为试验功能。</p>
      <p>后端总耗时用于比较整组问题的等待与处理时间，Jev 包含 Lambda 转发。整次请求另含浏览器网络。一次请求中的多个判断不拆分计时；GPT 不生成概率。</p>
      <p>历史数据只有 Decider，不计算三模型差异或速度倍数。仅预设图片的原始／换序对照显示样例预期；上传、无图和白图不评分。上传图片仅用于本次推理，应用不保存文件。</p>
    </details>`;
}

function comparisonSummary() {
  if (runMode === "recorded" && Object.keys(outcomes).length) return "Decider 已保存实测 · 点击“开始三模型对比”获取三列实时结果";
  const successful = providers.map((p) => outcomes[p.id]?.data).filter(Boolean);
  const failed = providers.filter((p) => outcomes[p.id]?.error).length;
  if (!Object.keys(outcomes).length) return "选择图片后，开始三模型对比";
  const sameInputs = successful.length === 3 && new Set(successful.map((d) => d.input_fingerprint)).size === 1;
  let compare = "";
  if (sameInputs) {
    const differences = Object.keys(successful[0].answers).filter((id) => new Set(successful.map((d) => answerValue(d.answers[id]))).size > 1).length;
    compare = differences ? `${differences} 项判断选择不同` : "本次各项判断选择相同";
  } else if (successful.length === 3) {
    compare = "输入指纹不同，本次不做配对比较";
  }
  return `<strong>${successful.length}/3 返回成功</strong>${failed ? ` · ${failed} 个模型失败` : ""}${busy ? " · 其余结果返回后立即显示" : ""}${compare ? ` · ${compare}` : ""}${totalMs == null ? "" : ` · 本轮等待 ${ms(totalMs)}`}`;
}

function modelCard(provider) {
  const outcome = outcomes[provider.id];
  const result = outcome?.data;
  return `<section class="vs-model-card ${provider.id}" data-v-provider="${provider.id}">
    <header class="vs-model-header"><h2>${provider.name}</h2><p>${result ? esc(result.model) : provider.detail}</p></header>
    ${result ? resultsMarkup(result) : outcome?.error ? `<div class="vs-error" role="alert"><strong>本模型调用失败</strong><p>${esc(outcome.error)}</p><small>失败请求耗时 ${ms(outcome.client_total_ms)}</small></div>` :
      `<div class="vs-empty">${outcome?.pending ? "正在读取图片并判断…" : runMode === "recorded" && Object.keys(outcomes).length ? "此列没有历史实测，运行对比后显示真实结果。" : "等待开始对比"}</div>`}
  </section>`;
}

function resultsMarkup(result) {
  const recorded = result.source === "recorded";
  const expected = result.expected;
  const correct = expected ? Object.entries(result.answers).filter(([id, a]) =>
    answerValue(a) === expected[id]).length : null;
  return `<div class="vs-source ${recorded ? "recorded" : "live"}"><strong>${recorded ? "历史实测" : "实时结果"}</strong>
      <span>${recorded ? esc(result.captured_at.slice(0, 10)) : "刚刚运行"} · ${esc(variants[result.variant])}</span></div>
    <div class="vs-metrics">
      <div><span>${recorded ? "采集时模型耗时" : "后端总耗时"}</span><strong data-v-backend-ms>${ms(recorded ? result.model_ms : result.backend_total_ms)}</strong></div>
      <div><span>${recorded ? "判断数量" : "整次请求（含网络）"}</span><strong>${recorded ? Object.keys(result.answers).length : ms(result.client_total_ms)}</strong></div>
    </div>
    <p class="vs-outcome-note">${expected ? `符合样例预期 <b>${correct}/${Object.keys(expected).length}</b>` : "本次不与原图标签评分"} · 输入 ${result.usage?.input_tokens ?? "—"} token</p>
    ${Object.entries(result.answers).sort(([a], [b]) => Number(b === "action") - Number(a === "action")).map(([id, answer]) => answerCard(id, answer, result)).join("")}
    <details class="vs-wire"><summary>查看完整问题、选项与返回</summary>
      <h3>实际输入（图片以摘要展示）</h3><pre>${esc(JSON.stringify({...result.request, protocol: result.protocol}, null, 2))}</pre>
      <h3>模型返回</h3><pre>${esc(JSON.stringify({model: result.model, answers: result.answers, raw_output: result.raw_output, usage: result.usage, model_ms: result.model_ms, provider_latency_ms: result.provider_latency_ms}, null, 2))}</pre>
    </details>`;
}

function answerCard(id, answer, result) {
  const expected = result.expected;
  const q = result.request.questions[id];
  const choice = answerValue(answer);
  const matched = expected ? choice === expected[id] : null;
  const probabilities = answer.type === "choice" ? answer.probabilities : typeof answer.noul === "number" ? {"是": answer.noul, "否": 1 - answer.noul} : null;
  return `<article class="vs-answer ${matched === false ? "different" : ""}" data-v-answer="${esc(id)}">
    <div class="vs-panel-heading"><h3>${esc(questionNames[id] || id)}</h3>${matched === null ? "" : `<span class="${matched ? "vs-match" : "vs-mismatch"}">${matched ? "符合预期" : "与预期不同"}</span>`}</div>
    <div class="vs-choice">${esc(chosenLabel(choice))}${answer.type === "choice" ? `<code>${esc(choice)}</code>` : ""}</div>
    ${matched === false ? `<p class="vs-expected">样例预期：${esc(chosenLabel(expected[id]))}</p>` : ""}
    ${probabilities ? `<p class="vs-confidence">${answer.type === "choice" ? "confidence" : "P(是)"}：${(100 * (answer.type === "choice" ? answer.confidence : answer.noul)).toFixed(1)}%</p>
    <details><summary>${answer.type === "choice" ? "候选项与概率" : "是／否概率"}</summary>
      <div class="vs-probabilities">${Object.entries(probabilities).map(([key, value]) => `<div>
        <div><span>${esc(labels[key] || key)}</span><b>${(100 * value).toFixed(1)}%</b></div>
        <div class="vs-bar"><i style="width:${Math.max(0, Math.min(100, value * 100))}%"></i></div>
        ${q.criteria?.[key] ? `<small>${esc(q.criteria[key])}</small>` : ""}</div>`).join("")}</div>
    </details>` : '<p class="vs-confidence">GPT 返回判断，不生成概率</p>'}</article>`;
}

async function run(mode) {
  if (busy || (mode === "recorded" && uploaded)) return;
  busy = true; error = ""; outcomes = {}; runMode = mode; totalMs = null;
  const version = ++revision;
  const active = mode === "recorded" ? providers.slice(0, 1) : providers;
  for (const p of active) outcomes[p.id] = {pending: true};
  render();
  const batchStarted = performance.now();
  await Promise.allSettled(active.map(async (provider) => {
  const started = performance.now();
  try {
    const body = {mode, provider: provider.id, variant, task: group, ...(uploaded ? {image: uploaded.base64} : {case_id: caseId})};
    const data = await ui.api("/api/vision/decide", body);
    if (version !== revision) return;
    outcomes[provider.id] = {data: {...data, client_total_ms: mode === "live" ? performance.now() - started : null}};
    if (mode === "live" && provider.id === "decider") connected = true;
  } catch (e) {
    if (version !== revision) return;
    outcomes[provider.id] = {error: e.message, status: e.status, client_total_ms: performance.now() - started};
    if (provider.id === "decider" && e.status >= 500) refreshHealth();
  } finally {
    render();
  }
  }));
  busy = false;
  totalMs = mode === "live" ? performance.now() - batchStarted : null;
  render();
}

function click(event) {
  const element = event.target.closest("button");
  if (!element) return;
  if (element.hasAttribute("data-v-run")) run("live");
  if (element.hasAttribute("data-v-recorded")) run("recorded");
  if (element.hasAttribute("data-v-health")) refreshHealth();
  if (element.hasAttribute("data-v-zoom")) {
    const dialog = document.createElement("dialog");
    dialog.className = "vs-image-dialog";
    dialog.innerHTML = `<button class="secondary-button">关闭</button><img alt="输入图片放大预览">`;
    dialog.querySelector("img").src = root.querySelector(".vs-image-wrap img").src;
    dialog.querySelector("button").onclick = () => dialog.close();
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }
  if (element.dataset.vGroup && !busy) {
    group = element.dataset.vGroup;
    caseId = uploaded ? null : catalog.cases.find((c) => c.group === group).id;
    outcomes = {}; error = ""; totalMs = null; render();
    if (!uploaded) run("recorded");
  }
  if (element.hasAttribute("data-v-export") && Object.keys(outcomes).length) {
    const url = URL.createObjectURL(new Blob([JSON.stringify({mode: runMode, task: group, variant, case_id: caseId, total_ms: totalMs, outcomes}, null, 2)], {type: "application/json"}));
    const link = document.createElement("a");
    link.href = url; link.download = `decider-image-${caseId || "upload"}-${variant}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

async function change(event) {
  if (busy) return;
  const target = event.target;
  if (target.hasAttribute("data-v-case") && target.value) {
    caseId = target.value; uploaded = null; error = ""; outcomes = {}; totalMs = null;
    render(); run("recorded");
  }
  if (target.hasAttribute("data-v-variant")) {
    variant = target.value; outcomes = {}; error = ""; totalMs = null; render();
    if (!uploaded) run("recorded");
  }
  if (target.hasAttribute("data-v-upload") && target.files?.[0]) {
    const file = target.files[0];
    busy = true;
    outcomes = {}; totalMs = null;
    render();
    try {
      if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
        throw new Error("请选择 PNG、JPEG 或 WebP 图片");
      if (file.size > 8 * 1024 * 1024) throw new Error("请选择小于 8 MB 的图片");
      const bitmap = await createImageBitmap(file);
      try {
        if (bitmap.width * bitmap.height > 4096 * 4096) throw new Error("图片像素过多，请缩小至 4096 × 4096 以内");
        const scale = Math.min(1, 448 / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement("canvas");
        canvas.width = 448;
        canvas.height = 448;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
        const width = Math.max(1, Math.round(bitmap.width * scale));
        const height = Math.max(1, Math.round(bitmap.height * scale));
        ctx.drawImage(bitmap, (448 - width) / 2, (448 - height) / 2, width, height);
        const url = canvas.toDataURL("image/png");
        uploaded = {url, base64: url.split(",")[1], name: file.name, width: canvas.width, height: canvas.height};
      } finally { bitmap.close(); }
      caseId = null; variant = "original"; outcomes = {}; error = "";
    } catch (e) {
      error = e.message || "无法读取该图片";
    } finally {
      busy = false;
      render();
    }
  }
}
