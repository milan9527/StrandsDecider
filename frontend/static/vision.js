let ui, catalog, root, loaded = false, loading = false, busy = false;
let group = "payment", caseId = "case-01", variant = "original";
let uploaded = null, result = null, error = "", connected = null, revision = 0;
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
    badge.textContent = connected ? "视觉服务已就绪" : "视觉服务暂不可用";
    badge.classList.toggle("ready", connected);
  }
}

function render() {
  const c = selectedCase();
  const source = variant === "blank" ? "/static/vision/blank.png" : uploaded?.url || c?.image_url;
  const questions = c?.questions || catalog.groups.find((g) => g.id === group).questions;
  root.innerHTML = `
    <div class="vs-heading"><div><span class="tiny-label">STRANDS DECIDER · VISION</span><h1>图片决策</h1>
      <p>选择或上传图片，查看模型的判断与耗时。</p></div>
      <button class="vs-health ${connected ? "ready" : ""}" data-v-health>${connected === null ? "检查视觉服务…" : connected ? "视觉服务已就绪" : "视觉服务暂不可用"}</button>
    </div>
    <div class="vs-tabs" role="group" aria-label="图片决策场景">${catalog.groups.map((g) =>
      `<button data-v-group="${g.id}" aria-pressed="${group === g.id}" class="${group === g.id ? "active" : ""}" ${lock()}>${esc(g.title)}</button>`).join("")}</div>
    <div class="vs-controls">
      <button class="primary-button" data-v-run ${lock()}>${ui.icon("play")}${busy ? "正在读取图片并判断…" : "运行图片决策"}</button>
      <button class="secondary-button" data-v-recorded ${lock()} ${uploaded ? "disabled" : ""}>查看已有实测</button>
      <label>对照方式<select data-v-variant ${lock()}>${Object.entries(variants).map(([id, text]) =>
        `<option value="${id}" ${id === variant ? "selected" : ""}>${text}</option>`).join("")}</select></label>
      <button class="text-button" data-v-export ${!result || busy ? "disabled" : ""}>导出结果</button>
    </div>
    ${error ? `<div class="vs-error" role="alert">${esc(error)}</div>` : ""}
    <div class="vs-layout">
      <section class="vs-image-panel"><div class="vs-panel-heading"><h2>输入图片</h2><span>${uploaded ? "自行上传" : "合成测试截图"}</span></div>
        <label class="vs-select-label">预设图片<select data-v-case ${lock()}>
          ${uploaded ? '<option value="" selected>当前上传图片</option>' : ""}
          ${catalog.cases.filter((item) => item.group === group).map((item) =>
            `<option value="${item.id}" ${item.id === caseId ? "selected" : ""}>${esc(item.title)}</option>`).join("")}
        </select></label>
        <div class="vs-image-wrap ${variant === "no_image" ? "omitted" : ""}">
          <img src="${esc(source)}" alt="${esc(uploaded?.name || c?.title || "待判断图片")}">
          ${variant === "no_image" ? '<div class="vs-image-overlay">本次请求不发送图片</div>' : ""}
        </div>
        <label class="secondary-button vs-upload">${ui.icon("plus")}上传图片<input type="file" data-v-upload accept="image/png,image/jpeg,image/webp" ${lock()}></label>
        <p class="vs-hint">${uploaded ? `${esc(uploaded.name)} · 已缩放至 ${uploaded.width} × ${uploaded.height}` : "PNG / JPEG / WebP · 最长边自动缩放至 448 像素"}</p>
      </section>
      <section class="vs-results" aria-live="polite" aria-busy="${busy}">
        ${result ? resultsMarkup() : `<div class="vs-empty"><h2>${busy ? "模型正在读取图片…" : "等待运行"}</h2><p>点击“运行图片决策”获取实时结果。</p>${Object.entries(questions).map(([id,q]) => `<div class="vs-question-preview"><strong>${esc(questionNames[id])}</strong><p>${esc(q.instructions)}</p></div>`).join("")}</div>`}
      </section>
    </div>
    <details class="vs-notes"><summary>查看测试口径与模型信息</summary>
      <p>实时推理由独立的官方 v19 视觉服务执行；现有文字模块继续使用 vLLM。上传图片仅用于本次推理，应用不保存文件。</p>
      <p>历史实测采集于 2026-10-23，共 12 张清晰合成截图。仅预设图片的原始／换序对照显示样例预期；自行上传、无图和白图不统计预期一致。</p>
      <p>一次请求包含本场景全部问题，耗时不拆分或平均到每个判断。概率用于观察模型判断，不代表业务保证。</p>
    </details>`;
}

function resultsMarkup() {
  const recorded = result.source === "recorded";
  const expected = result.expected;
  const correct = expected ? Object.entries(result.answers).filter(([id, a]) =>
    (a.type === "choice" ? a.choice : a.noul >= .5) === expected[id]).length : null;
  return `<div class="vs-source ${recorded ? "recorded" : "live"}"><strong>${recorded ? "历史实测" : "实时结果"}</strong>
      <span>${recorded ? esc(result.captured_at.slice(0, 10)) : "刚刚运行"} · ${esc(variants[result.variant])}</span></div>
    <div class="vs-metrics">
      <div><span>${recorded ? "采集时模型耗时" : "模型耗时"}</span><strong>${ms(result.model_ms)}</strong></div>
      <div><span>${recorded ? "判断数量" : "后端总耗时"}</span><strong>${recorded ? Object.keys(result.answers).length : ms(result.backend_total_ms)}</strong></div>
      <div><span>${expected ? "符合样例预期" : "输入 token"}</span><strong>${expected ? `${correct} / ${Object.keys(expected).length}` : result.usage?.input_tokens ?? "—"}</strong></div>
    </div>
    ${Object.entries(result.answers).sort(([a], [b]) => Number(b === "action") - Number(a === "action")).map(([id, answer]) => answerCard(id, answer, expected)).join("")}
    <details class="vs-wire"><summary>查看完整问题、选项与返回</summary>
      <h3>实际请求</h3><pre>${esc(JSON.stringify(result.request, null, 2))}</pre>
      <h3>模型返回</h3><pre>${esc(JSON.stringify({model: result.model, answers: result.answers, usage: result.usage}, null, 2))}</pre>
    </details>`;
}

function answerCard(id, answer, expected) {
  const q = result.request.questions[id];
  const choice = answer.type === "choice" ? answer.choice : answer.noul >= .5;
  const matched = expected ? choice === expected[id] : null;
  const probabilities = answer.type === "choice" ? answer.probabilities : {"是": answer.noul, "否": 1 - answer.noul};
  return `<article class="vs-answer ${matched === false ? "different" : ""}" data-v-answer="${esc(id)}">
    <div class="vs-panel-heading"><h3>${esc(questionNames[id] || id)}</h3>${matched === null ? "" : `<span class="${matched ? "vs-match" : "vs-mismatch"}">${matched ? "符合预期" : "与预期不同"}</span>`}</div>
    <p class="vs-question">${esc(q.instructions)}</p>
    <div class="vs-choice">${esc(chosenLabel(choice))}${answer.type === "choice" ? `<code>${esc(choice)}</code>` : ""}</div>
    ${matched === false ? `<p class="vs-expected">样例预期：${esc(chosenLabel(expected[id]))}</p>` : ""}
    <p class="vs-confidence">${answer.type === "choice" ? "confidence" : "P(是)"}：${(100 * (answer.type === "choice" ? answer.confidence : answer.noul)).toFixed(1)}%</p>
    <details><summary>${answer.type === "choice" ? "候选项与概率" : "是／否概率"}</summary>
      <div class="vs-probabilities">${Object.entries(probabilities).map(([key, value]) => `<div>
        <div><span>${esc(labels[key] || key)}</span><b>${(100 * value).toFixed(1)}%</b></div>
        <div class="vs-bar"><i style="width:${Math.max(0, Math.min(100, value * 100))}%"></i></div>
        ${q.criteria?.[key] ? `<small>${esc(q.criteria[key])}</small>` : ""}</div>`).join("")}</div>
    </details></article>`;
}

async function run(mode) {
  if (busy || (mode === "recorded" && uploaded)) return;
  busy = true; error = ""; result = null;
  const version = ++revision;
  render();
  try {
    const body = {mode, variant, task: group, ...(uploaded ? {image: uploaded.base64} : {case_id: caseId})};
    const started = performance.now();
    const data = await ui.api("/api/vision/decide", body);
    if (version !== revision) return;
    result = {...data, client_total_ms: mode === "live" ? performance.now() - started : null};
    if (mode === "live") connected = true;
  } catch (e) {
    if (version !== revision) return;
    error = e.message;
    if (e.status >= 500) refreshHealth();
  } finally {
    busy = false;
    render();
  }
}

function click(event) {
  const element = event.target.closest("button");
  if (!element) return;
  if (element.hasAttribute("data-v-run")) run("live");
  if (element.hasAttribute("data-v-recorded")) run("recorded");
  if (element.hasAttribute("data-v-health")) refreshHealth();
  if (element.dataset.vGroup && !busy) {
    group = element.dataset.vGroup;
    caseId = uploaded ? null : catalog.cases.find((c) => c.group === group).id;
    result = null; error = ""; render();
    if (!uploaded) run("recorded");
  }
  if (element.hasAttribute("data-v-export") && result) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: "application/json"}));
    const link = document.createElement("a");
    link.href = url; link.download = `decider-image-${caseId || "upload"}-${variant}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

async function change(event) {
  if (busy) return;
  const target = event.target;
  if (target.hasAttribute("data-v-case") && target.value) {
    caseId = target.value; uploaded = null; error = ""; result = null;
    render(); run("recorded");
  }
  if (target.hasAttribute("data-v-variant")) {
    variant = target.value; result = null; error = ""; render();
    if (!uploaded) run("recorded");
  }
  if (target.hasAttribute("data-v-upload") && target.files?.[0]) {
    const file = target.files[0];
    busy = true;
    result = null;
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
        canvas.width = Math.max(1, Math.round(bitmap.width * scale));
        canvas.height = Math.max(1, Math.round(bitmap.height * scale));
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        const url = canvas.toDataURL("image/png");
        uploaded = {url, base64: url.split(",")[1], name: file.name, width: canvas.width, height: canvas.height};
      } finally { bitmap.close(); }
      caseId = null; variant = "original"; result = null; error = "";
    } catch (e) {
      error = e.message || "无法读取该图片";
    } finally {
      busy = false;
      render();
    }
  }
}
