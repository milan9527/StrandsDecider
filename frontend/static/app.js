import { mountCrypto } from "/static/crypto.js?v=triple1";

const paths = {
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  shield:
    '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  history: '<path d="M3 11a9 9 0 1 1 2.6 7M3 4v7h7"/><path d="M12 7v5l3 2"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  "arrow-up-right": '<path d="M7 17 17 7M7 7h10v10"/>',
  "arrow-right": '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  refresh:
    '<path d="M20 7a9 9 0 0 0-15-1L3 9m0-6v6h6m-5 8a9 9 0 0 0 15 1l2-3m0 6v-6h-6"/>',
  rotate: '<path d="M3 10a9 9 0 1 1 2 9M3 3v7h7"/>',
  github:
    '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-4a3.5 3.5 0 0 0-1-2.7c3.3-.4 6.8-1.6 6.8-7.3a5.7 5.7 0 0 0-1.5-4 5.2 5.2 0 0 0-.1-4s-1.3-.4-4.2 1.5a14.4 14.4 0 0 0-7 0C6-.4 4.7 0 4.7 0a5.2 5.2 0 0 0-.1 4A5.7 5.7 0 0 0 3 8c0 5.7 3.5 6.9 6.8 7.3A3.5 3.5 0 0 0 9 18v4" transform="translate(1 2) scale(.9)"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="3"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v3m6-3v3m4 4h3m-3 6h3M9 19v3m6-3v3M2 9h3m-3 6h3"/>',
  route:
    '<circle cx="5" cy="5" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M5 7v8a3 3 0 0 0 3 3h9M5 12h6a4 4 0 0 0 4-4V6h2"/>',
  "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  sliders:
    '<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  zap: '<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>',
  inbox: '<path d="m3 12 3-8h12l3 8v8H3zM3 12h5l2 3h4l2-3h5"/>',
  heart:
    '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  play: '<path d="m8 5 11 7-11 7z"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  sparkles:
    '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 2v4m-2-2h4"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  lightbulb: '<path d="M9 18h6m-6 3h6M8 14a7 7 0 1 1 8 0l-1 4H9z"/>',
  message:
    '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5A8.5 8.5 0 0 1 10.5 3h2a8.5 8.5 0 0 1 8.5 8.5z"/><path d="M7 9h10M7 13h6"/>',
  wrench: '<path d="m14 6 4 4 4-4a7 7 0 0 1-9 9l-7 7-4-4 7-7a7 7 0 0 1 9-9z"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
};
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.grid}</svg>`;
function hydrateIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => {
    el.innerHTML = icon(el.dataset.icon);
  });
}
const pct = (n) => `${(n * 100).toFixed(1)}%`;
const json = (value) => JSON.stringify(value, null, 2);
const names = {
  playground: "决策工作台",
  guard: "工具调用守卫",
  crypto: "支付流程对比",
  history: "运行记录",
  about: "理解 Decider",
};
const initialEmpty = $("#results").innerHTML;
let examples = [],
  selected = null,
  questions = [],
  mode = "example",
  result = null,
  lastRequest = null;
let resultTab = "visual",
  running = false,
  guardRunning = false,
  currentPage = "playground";
let guardResult = null;
let history = [];
let currentUser = null;
let historyKey = null;
let scenarioCategory = "all";
let gpuState = null;
let gpuChecking = false;
let gpuChanging = false;
let gpuError = "";
let gpuActionError = "";
let gpuRequest = null;
let gpuFailureCheck = null;

function renderGpu() {
  window.dispatchEvent(new Event("decider-gpu-state"));
  const unavailable = !!gpuError || !gpuState;
  const enabled = gpuState?.enabled;
  $("#gpu-open").hidden = !currentUser || (gpuState && !enabled && !gpuError);
  $("#gpu-launcher-label").textContent = `GPU · ${
    gpuError
      ? "状态未知"
      : !gpuState
        ? "检查中"
        : {
            stopped: "未启动",
            starting: "启动中",
            ready: gpuState.desired === "running" ? "已就绪" : "停止中",
            stopping: "停止中",
            error: "启动失败",
          }[gpuState.phase] || "未启用"
  }`;
  $("#gpu-open").classList.toggle(
    "ready",
    !unavailable &&
      gpuState?.phase === "ready" &&
      gpuState.desired === "running",
  );
  $("#gpu-action-error").hidden = !gpuActionError;
  $("#gpu-action-error").textContent = gpuActionError;
  $("#gpu-refresh").disabled = gpuChecking || gpuChanging;
  $("#gpu-start").hidden = !enabled || !gpuState.can_manage;
  $("#gpu-stop").hidden =
    !enabled ||
    !gpuState.can_manage ||
    (gpuState.desired !== "running" && gpuState.phase !== "stopping");
  $("#gpu-start").disabled =
    unavailable ||
    gpuChecking ||
    gpuChanging ||
    !["stopped", "error"].includes(gpuState?.phase);
  $("#gpu-stop").disabled =
    unavailable ||
    gpuChecking ||
    gpuChanging ||
    gpuState?.desired !== "running";
  $("#gpu-access-hint").hidden = !enabled || gpuState.can_manage;
  if (unavailable || !enabled) {
    $("#gpu-status").textContent = gpuError
      ? "状态暂不可用"
      : !gpuState
        ? "检查中"
        : "未启用";
    $("#gpu-message").textContent = gpuError
      ? `无法确认 GPU 状态：${gpuError}。请刷新后重试。`
      : !gpuState
        ? "正在读取 GPU 状态…"
        : "此环境未配置按需 GPU 管理。";
    $("#gpu-spec").textContent = "";
    return;
  }
  const phase = gpuState.phase;
  const sageMaker = gpuState.provider === "sagemaker";
  const autoStop = gpuState.idle_auto_stop !== false;
  const idleMinutes = gpuState.idle_minutes ?? 30;
  const lifecycle = autoStop
    ? `闲置 ${idleMinutes} 分钟自动停止`
    : "持续运行 · 手动停止";
  $("#gpu-heading-label").textContent = sageMaker
    ? "SageMaker GPU · 按需运行"
    : autoStop
      ? "GPU · 按需实例"
      : "GPU · 按需计费 · 持续运行";
  $("#gpu-stop").textContent = sageMaker
    ? "停止 SageMaker GPU"
    : "停止 GPU，保留磁盘";
  const waitingCapacity = gpuState.startup_stage === "waiting_capacity";
  const labels = {
    stopped: "已停止",
    starting: waitingCapacity ? "等待 GPU 容量" : "启动中",
    ready: "GPU 就绪",
    stopping: "停止中",
    error: "启动未完成",
  };
  $("#gpu-status").textContent = labels[phase] || "检查中";
  $("#gpu-spec").textContent =
    `${gpuState.instance_type} · 按需约 $${gpuState.instance_usd_per_hour}/小时 · 80GB 磁盘约 $${gpuState.disk_usd_per_month.toFixed(2)}/月 · ${lifecycle}`;
  const capacityRetry =
    gpuState.instance_options?.length === 1
      ? `正在重试 ${gpuState.instance_type}，不会切换到其他规格`
      : "正在同一实例上轮换兼容规格重试";
  const minutes = Math.ceil(gpuState.idle_remaining_seconds / 60);
  const messages = {
    stopped: gpuState.disk_retained
      ? "GPU 已停止，磁盘和模型缓存已保留。下次启动将复用同一实例；示例回放仍可使用。"
      : "示例回放可直接使用。首次启动将创建按需 GPU 并下载模型；之后停止时保留磁盘和缓存。",
    starting: waitingCapacity
      ? `AWS 当前可用区 GPU 容量不足，实例尚未启动。${capacityRetry}，磁盘保留。已等待 ${Math.floor((gpuState.startup_elapsed_seconds || 0) / 60)} 分钟，最多再等待 ${Math.ceil((gpuState.startup_remaining_seconds || 0) / 60)} 分钟。保留磁盘不会预留 GPU 容量，可点击停止取消等待。`
      : gpuState.startup_stage === "loading_model"
        ? "GPU 实例已运行，正在加载模型并等待健康检查。"
        : "正在启动按需 GPU，随后加载模型。首次需要下载镜像；超过 20 分钟未就绪会自动停止并保留磁盘。",
    ready: gpuState.busy
      ? "正在执行推理。停止操作会等待当前请求完成。"
      : autoStop
        ? `真实模型已就绪。若没有新的推理请求，约 ${minutes} 分钟后自动停止并保留磁盘。`
        : "真实模型已就绪。GPU 持续运行并按需计费，不因闲置自动停止；可手动停止并保留磁盘。",
    stopping:
      "已停止接收新的推理请求，正在等待任务结束并停止 EC2，磁盘和模型缓存会保留。",
    error: waitingCapacity
      ? "等待 AWS GPU 容量已超时，实例未能启动。磁盘和缓存已保留，可稍后重试；保留磁盘不保证下次有可用 GPU。"
      : "本次启动未在时限内完成，GPU 已停止。已创建的磁盘会保留，可重新尝试启动。",
  };
  $("#gpu-message").textContent = messages[phase] || "正在检查资源状态。";
  if (sageMaker) {
    $("#gpu-spec").textContent =
      `${gpuState.instance_type} · 约 $${gpuState.instance_usd_per_hour}/小时 · ${lifecycle}` +
      (gpuState.disk_retained
        ? ` · 原 EC2 磁盘保留，约 $${gpuState.disk_usd_per_month.toFixed(2)}/月`
        : "");
    const sageMakerMessages = {
      stopped:
        "SageMaker GPU 已停止，模型镜像已保留。再次启动会创建新的推理实例；示例回放仍可使用。",
      starting: `SageMaker 正在申请 GPU 并加载模型（${gpuState.endpoint_status || "准备中"}）。已等待 ${Math.floor((gpuState.startup_elapsed_seconds || 0) / 60)} 分钟，超过 20 分钟未就绪会自动请求停止。`,
      ready: gpuState.busy
        ? "正在执行真实 GPU 推理。停止操作会等待当前请求结束。"
        : `SageMaker 模型已就绪，约 ${minutes} 分钟无推理请求后自动停止。`,
      stopping:
        gpuState.endpoint_status === "Creating"
          ? "已请求停止。AWS 不支持取消正在创建的 Endpoint，正在等待创建流程结束后自动删除；清理完成前不会启动第二台 GPU。"
          : "正在等待推理结束并删除 SageMaker 推理 Endpoint，完成后停止 GPU 计算计费。模型镜像继续保留。",
      error: gpuState.last_error_message
        ? `SageMaker 启动失败：${gpuState.last_error_message}`
        : "SageMaker 未在时限内就绪，推理 Endpoint 已清理。模型镜像已保留，可重新尝试。",
    };
    $("#gpu-message").textContent =
      sageMakerMessages[phase] || "正在检查 SageMaker 状态。";
  }
}

function checkGpu() {
  if (gpuRequest) return gpuRequest;
  if (!currentUser || gpuChanging) return Promise.resolve();
  gpuChecking = true;
  renderGpu();
  gpuRequest = (async () => {
    try {
      const previous = gpuState?.phase;
      gpuState = await api("/api/gpu");
      gpuError = "";
      if (previous !== gpuState.phase) checkConnection();
    } catch (error) {
      gpuError = error.message;
    } finally {
      gpuChecking = false;
      gpuRequest = null;
      renderGpu();
    }
  })();
  return gpuRequest;
}

async function changeGpu(action) {
  if (gpuChanging || gpuChecking || gpuError || !gpuState?.can_manage) return;
  if (action === "start" && !["stopped", "error"].includes(gpuState.phase))
    return;
  if (action === "stop" && gpuState.desired !== "running") return;
  gpuChanging = true;
  gpuActionError = "";
  renderGpu();
  try {
    gpuState = await api(`/api/gpu/${action}`, {});
    gpuError = "";
    renderGpu();
    checkConnection();
    toast(
      action === "start"
        ? "启动请求已提交，页面会自动更新状态。"
        : "停止请求已提交，将等待当前推理完成。",
    );
  } catch (error) {
    gpuActionError = error.message;
    toast(error.message);
  } finally {
    gpuChanging = false;
    renderGpu();
  }
}

function openGpuDialog(context = "", refresh = true) {
  if (!currentUser) return;
  $("#gpu-dialog-context").textContent =
    context || "所有模块共用同一台 Decider GPU。";
  renderGpu();
  if (!$("#gpu-dialog").open) $("#gpu-dialog").showModal();
  if (refresh) checkGpu();
}

async function ensureGpuReady(context = "") {
  // Always-on inference never waits for the management API. Unknown initial
  // state also goes directly to the backend, which enforces readiness/leases.
  if (!gpuState || gpuState.idle_auto_stop === false) return true;
  await checkGpu();
  if (
    !gpuError &&
    !gpuChanging &&
    gpuState &&
    (!gpuState.enabled ||
      (gpuState.phase === "ready" && gpuState.desired === "running"))
  )
    return true;
  const message = gpuError
    ? "无法确认 GPU 状态，请刷新后重试。"
    : "GPU 尚未就绪，请先启动并等待状态变为“GPU 就绪”。";
  openGpuDialog(
    `${context || "真实推理"}需要 Decider GPU，请在下方查看状态并启动。`,
    false,
  );
  toast(message);
  return false;
}

function diagnoseGpuFailure() {
  if (gpuFailureCheck || !currentUser || $("#gpu-dialog").open) return;
  gpuFailureCheck = (async () => {
    await checkGpu();
    if (!currentUser || gpuState?.enabled === false) return;
    if (
      gpuError ||
      !gpuState ||
      gpuState.phase !== "ready" ||
      gpuState.desired !== "running"
    )
      openGpuDialog(
        "本次模型调用失败。请查看 GPU 状态；恢复就绪后，可返回重新运行。",
        false,
      );
  })().finally(() => {
    gpuFailureCheck = null;
  });
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    el.hidden = true;
  }, 3500);
}
async function api(path, body) {
  const started = performance.now();
  const deciderRequest =
    body?.mode === "live" &&
    (["/api/decide", "/api/guard"].includes(path) ||
      (["/api/crypto/decision", "/api/crypto/loop/tick"].includes(path) &&
        body.provider === "decider"));
  const failure = (message, status) => {
    if (deciderRequest && (status === undefined || status >= 500))
      diagnoseGpuFailure();
    return Object.assign(new Error(message), { status });
  };
  let response;
  try {
    response = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body
        ? { "Content-Type": "application/json", "X-Decider-Client": "web" }
        : {},
      credentials: "same-origin",
      cache: "no-store",
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(body ? 195000 : 7000),
    });
  } catch (error) {
    throw failure(
      error.name === "TimeoutError"
        ? "请求超时，请检查服务状态后重试。"
        : "无法连接演示服务，请确认 Web 服务正在运行。",
    );
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw failure(
      "服务返回了无法读取的响应。",
      response.ok ? undefined : response.status,
    );
  }
  if (!response.ok) {
    if (response.status === 401 && currentUser) {
      $("#gpu-dialog").close();
      document.body.classList.add("auth-pending");
      location.reload();
    }
    let detail = data.detail;
    if (Array.isArray(detail))
      detail = detail
        .map((x) => `${x.loc?.slice(1).join(".")}: ${x.msg}`)
        .join("；");
    throw failure(
      typeof detail === "string" ? detail : `请求失败 (${response.status})`,
      response.status,
    );
  }
  if (path === "/api/decide" || path === "/api/guard") {
    data.timings = {
      ...data.timings,
      client_total_ms: Number((performance.now() - started).toFixed(3)),
    };
  }
  return data;
}
function showPage() {
  $("#gpu-dialog").close();
  currentPage =
    location.hash.slice(1) in names ? location.hash.slice(1) : "playground";
  $$(".page").forEach((p) => {
    p.hidden = p.id !== `page-${currentPage}`;
  });
  $$("[data-page]").forEach((el) => {
    const active = el.dataset.page === currentPage;
    el.classList.toggle("active", active);
    if (active) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  $("#breadcrumb-page").textContent = names[currentPage];
  renderGpu();
  if (currentPage === "history") renderHistory();
  if (currentPage === "crypto" && currentUser)
    mountCrypto({
      api,
      esc,
      icon,
      toast,
      gpu: () => ({
        state: gpuState,
        checking: gpuChecking || gpuChanging,
        error: gpuError,
      }),
      openGpuDialog,
      ensureGpuReady,
    });
}

async function checkConnection() {
  const el = $("#connection"),
    button = $("#refresh-connection");
  button.disabled = true;
  el.innerHTML = '<span class="status-dot pending"></span>检查模型连接';
  try {
    const data = await api("/api/health");
    el.innerHTML = data.connected
      ? `<span class="status-dot"></span>模型已连接 · ${esc(data.upstream.device || "ready")}`
      : '<span class="status-dot offline"></span>示例就绪 · 模型未连接';
    el.title = data.connected
      ? data.upstream.model
      : "模型尚未就绪，请稍后刷新连接。";
  } catch (e) {
    el.innerHTML = '<span class="status-dot offline"></span>Web 服务未连接';
    el.title = e.message;
  } finally {
    button.disabled = false;
  }
}
function selectExample(id) {
  if (running) return;
  selected = examples.find((x) => x.id === id);
  if (!selected) return;
  questions = Object.entries(structuredClone(selected.questions)).map(
    ([id, question]) => ({ id, ...question }),
  );
  $("#state-input").value = selected.state;
  $("#run-decision").disabled = false;
  $("#scenario-guide").hidden = false;
  $("#selected-category").textContent = selected.category || "基础场景";
  $("#selected-scenario-title").textContent = selected.title;
  $("#run-scenario").textContent = selected.title;
  $("#selected-question-count").textContent = `${questions.length} 个决策`;
  $("#scenario-description").textContent =
    selected.description || selected.subtitle;
  $("#scenario-suggestion").textContent =
    selected.suggestion || "修改上下文，观察判断如何变化。";
  $$(".scenario-card").forEach((el) => {
    el.classList.toggle("active", el.dataset.example === id);
    el.setAttribute("aria-pressed", String(el.dataset.example === id));
  });
  renderQuestions();
  countChars();
  invalidate();
}
function renderScenarios() {
  const search = $("#scenario-search").value.trim().toLowerCase();
  const categories = [
    ...new Set(examples.map((example) => example.category || "基础场景")),
  ];
  $("#scenario-filters").innerHTML = [
    { id: "all", label: "全部场景", count: examples.length },
    ...categories.map((category) => ({
      id: category,
      label: category,
      count: examples.filter(
        (example) => (example.category || "基础场景") === category,
      ).length,
    })),
  ]
    .map(
      (category) =>
        `<button type="button" data-category="${esc(category.id)}" class="scenario-filter ${scenarioCategory === category.id ? "active" : ""}" aria-pressed="${scenarioCategory === category.id}">${esc(category.label)}<span>${category.count}</span></button>`,
    )
    .join("");
  const visible = examples.filter((example) => {
    const categoryMatches =
      scenarioCategory === "all" ||
      (example.category || "基础场景") === scenarioCategory;
    const text = [
      example.id,
      example.title,
      example.subtitle,
      example.category,
      example.description,
      example.state,
    ]
      .join(" ")
      .toLowerCase();
    return categoryMatches && text.includes(search);
  });
  $("#scenario-count").textContent =
    `显示 ${visible.length} / ${examples.length} 个场景 · 支持示例回放与真实推理`;
  $("#scenarios").innerHTML = visible.length
    ? visible
        .map((example) => {
          const active = selected?.id === example.id;
          return `<button class="scenario-card ${active ? "active" : ""}" data-example="${esc(example.id)}" aria-pressed="${active}">
      <span class="scenario-icon">${icon(example.icon)}</span><div><h3>${esc(example.title)}</h3><p>${esc(example.subtitle)}</p><span class="tag">${esc(example.tag)} · ${Object.keys(example.questions).length} 个决策</span></div><span class="scenario-check"></span></button>`;
        })
        .join("")
    : `<div class="scenario-empty">${icon("search")}<h3>没有匹配的场景</h3><p>尝试其他关键词，或查看全部场景。</p><button type="button" class="secondary-button" id="clear-scenario-filters">清除筛选</button></div>`;
}
function countChars() {
  $("#char-count").textContent =
    `${$("#state-input").value.length.toLocaleString()} / 12,000`;
}
function invalidate() {
  result = null;
  lastRequest = null;
  $("#result-status").textContent = "等待运行";
  $("#result-status").className = "subtle-badge";
  $("#copy-result").disabled = true;
  $("#results").innerHTML = initialEmpty;
  hydrateIcons($("#results"));
}
function criteriaFor(type) {
  return type === "choice"
    ? { option_a: "First option", option_b: "Second option" }
    : type === "score"
      ? ["Low", "Medium", "High"]
      : undefined;
}
function renderQuestions() {
  $("#run-question-count").textContent = `${questions.length} 个问题`;
  $("#question-count").textContent = questions.length;
  $("#add-question").disabled = questions.length >= 8;
  $("#questions").innerHTML = questions
    .map((q, i) => {
      const options =
        q.type === "noul"
          ? ["true", "false"]
          : q.type === "score"
            ? q.criteria
            : Object.keys(q.criteria);
      return `<article class="question-card" data-question="${i}">
      <div class="question-top"><select class="type-badge ${esc(q.type)}" aria-label="问题 ${i + 1} 类型" data-edit="type">
        ${["choice", "noul", "score"].map((type) => `<option value="${type}" ${q.type === type ? "selected" : ""}>${type}</option>`).join("")}
      </select><span class="question-key">${esc(q.id)}</span><button class="icon-button" data-remove="${i}" aria-label="删除问题 ${i + 1}" ${questions.length === 1 ? "disabled" : ""}>${icon("trash")}</button></div>
      <input class="question-instructions" data-edit="instructions" aria-label="问题 ${i + 1} 指令" value="${esc(q.instructions)}" maxlength="1000" placeholder="用自然语言描述这个问题…">
      <div class="option-chips">${options.map((label) => `<span class="option-chip"><i class="chip-dot"></i>${esc(label)}</span>`).join("")}</div>
      <details class="question-editor"><summary>编辑选项与说明</summary>
        <textarea data-edit="criteria" aria-label="问题 ${i + 1} 选项 JSON" spellcheck="false" rows="3">${esc(q.criteriaDraft ?? json(q.criteria || { true: "The answer is yes", false: "The answer is no" }))}</textarea>
        <p>${q.type === "score" ? "JSON 数组，等级从低到高排列。" : q.type === "noul" ? '可选 JSON 对象，键为 "true"、"false"。' : "JSON 对象：选项名称 → 含义描述。"}</p>
      </details>
    </article>`;
    })
    .join("");
}
function collectRequest() {
  const wireQuestions = {};
  for (const q of questions) {
    let criteria = q.criteria;
    if (q.criteriaDraft !== undefined) {
      try {
        criteria = JSON.parse(q.criteriaDraft);
      } catch {
        throw new Error(`${q.id} 的选项不是有效 JSON，请检查括号和引号。`);
      }
    }
    if (!q.instructions.trim()) throw new Error(`${q.id} 的问题指令不能为空。`);
    wireQuestions[q.id] = {
      type: q.type,
      instructions: q.instructions.trim(),
      ...(criteria !== undefined ? { criteria } : {}),
    };
  }
  return {
    mode,
    measure_decisions: true,
    example_id: selected?.id,
    state: $("#state-input").value,
    questions: wireQuestions,
  };
}
function setMode(next) {
  if (running || guardRunning) {
    toast("请等待当前请求完成后再切换模式。");
    return;
  }
  mode = next;
  $$("[data-mode]").forEach((el) => {
    el.classList.toggle("active", el.dataset.mode === mode);
    el.setAttribute("aria-pressed", String(el.dataset.mode === mode));
  });
  $("#mode-caption").textContent =
    mode === "live"
      ? "逐项调用真实模型并记录耗时；总时间包含网络与排队。逐项执行可能比批量执行慢。"
      : "示例回放使用预设数据，不调用模型。修改输入后请切换到真实模型。";
  if (mode === "live") checkConnection();
}
function sourceBanner(data) {
  return `<div class="source-banner ${data.source === "live" ? "live" : ""}">${icon(data.source === "live" ? "check-circle" : "info")}<span>${data.source === "live" ? `真实推理 · ${esc(data.model)}` : "预设示例数据 · 非模型推理 · 未调用模型"}</span></div>`;
}
function duration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  if (ms > 0 && ms < 0.1) return "< 0.1 ms";
  return `${ms.toFixed(1)} ms`;
}
function totalDuration(data) {
  return data.timings?.client_total_ms ?? data.timings?.backend_total_ms;
}
function decisionTiming(data, key) {
  if (data.source !== "live") return "示例 · 未推理";
  const elapsed = data.timings?.decisions_ms?.[key];
  return Number.isFinite(elapsed)
    ? `耗时 ${duration(elapsed)}`
    : data.timings?.execution === "batch"
      ? "批量 · 未单独计时"
      : "耗时未记录";
}
function startRunTimer(container) {
  const started = performance.now();
  const timer = document.createElement("span");
  timer.className = "running-elapsed";
  timer.setAttribute("role", "timer");
  timer.setAttribute("aria-live", "off");
  const update = () => {
    timer.textContent = `已用时间 ${duration(performance.now() - started)}`;
  };
  update();
  $(".result-loading", container).append(timer);
  const interval = setInterval(update, 100);
  return () => clearInterval(interval);
}
function bars(probabilities, winner, legend = {}) {
  return Object.entries(probabilities)
    .map(
      ([
        key,
        value,
      ]) => `<div class="probability-row ${key === winner ? "winner" : ""}">
    <span title="${esc(legend[key] || key)}">${esc(legend[key] || key)}</span>
    <div class="probability-track"><div class="probability-fill" style="width:${value * 100}%"></div></div><span>${pct(value)}</span>
  </div>`,
    )
    .join("");
}
function renderAnswer(key, answer, data, label = key) {
  const title = `<div class="answer-title"><span class="type-badge ${esc(answer.type)}">${esc(answer.type)}</span><span class="answer-id">${esc(label)}</span><span class="answer-duration">${decisionTiming(data, key)}</span></div>`;
  if (answer.type === "noul") {
    const uncertain = Math.abs(answer.noul - 0.5) < 0.05;
    return `<article class="answer-card">${title}<div class="answer-value"><strong>${uncertain ? "不确定" : answer.noul >= 0.5 ? "是 · Yes" : "否 · No"}</strong><span>P(true)</span><b class="confidence-badge">${pct(answer.noul)}</b></div>
      <div class="noul-track"><div class="noul-fill" style="width:${answer.noul * 100}%"></div></div><div class="noul-labels"><span>0 · False</span><span>1 · True</span></div>
      <p class="answer-explainer">返回“是”的概率，接近 0.5 表示不确定。</p></article>`;
  }
  if (answer.type === "choice") {
    return `<article class="answer-card">${title}<div class="answer-value"><strong>${esc(answer.choice)}</strong><b class="confidence-badge">confidence ${pct(answer.confidence)}</b></div>
      ${bars(answer.probabilities, answer.choice)}<p class="answer-explainer">confidence 由最高选项概率归一化得到，与选项概率不同。</p></article>`;
  }
  const levels = Object.values(answer.legend);
  return `<article class="answer-card">${title}<div class="answer-value"><strong>${answer.score.toFixed(2)}</strong><span>/ ${levels.length - 1}</span><b class="confidence-badge">confidence ${pct(answer.confidence)}</b></div>
    <div class="score-bar"><div class="score-marker" style="left:${(answer.score / (levels.length - 1)) * 100}%"></div></div>
    <div class="score-ruler"><span>0 · ${esc(levels[0])}</span><span>${levels.length - 1} · ${esc(levels.at(-1))}</span></div>
    <p class="answer-explainer">有序等级的期望值；confidence 反映分布的集中程度。</p>
    ${bars(answer.probabilities, String(Math.round(answer.score)), answer.legend)}</article>`;
}
function metrics(data) {
  const live = data.source === "live";
  const clientMeasured = Number.isFinite(data.timings?.client_total_ms);
  return `<div class="run-metrics"><div class="total-duration"><label>${clientMeasured ? "总时间" : "后端总时间"}</label><strong>${duration(totalDuration(data))}</strong></div><div><label>模型处理耗时${data.timings?.execution === "individual" ? "合计" : ""}</label><strong>${live ? duration(data.latency_ms) : "未调用模型"}</strong></div><div><label>输入 tokens</label><strong>${live ? esc(data.usage?.input_tokens ?? "—") : "—"}</strong></div><div><label>决策数量</label><strong>${Object.keys(data.answers).length}</strong></div></div>
    <p class="timing-note">${live ? (data.timings?.execution === "individual" ? "每项耗时为该项模型请求到校验完成的实测时间。" : "批量运行共用一次模型请求，不单独分摊耗时。") : "示例结果为预设数据，每项无推理耗时；总时间仅表示读取示例的请求时间。"}${clientMeasured ? "总时间从发起请求到收到结果，包含网络、排队和处理开销。" : ""}</p>`;
}
function requestCode(request) {
  const wire = {
    mode: "live",
    measure_decisions: true,
    state: request.state,
    questions: request.questions,
  };
  // This is displayed text, not executed code.
  return `# 先按 README 登录并保存会话到 cookies.txt\n# 将请求保存为 request.json 后执行：\ncurl ${location.origin}/api/decide \\\n  -b cookies.txt \\\n  -H 'X-Decider-Client: web' \\\n  -H 'Content-Type: application/json' \\\n  --data-binary @request.json\n\n# request.json\n${json(wire)}`;
}
function renderResults() {
  if (!result) return;
  $("#copy-result").disabled = false;
  $("#results").innerHTML =
    resultTab === "visual"
      ? `<div class="results-body">${sourceBanner(result)}${Object.entries(
          result.answers,
        )
          .map(([k, a]) => renderAnswer(k, a, result))
          .join("")}${metrics(result)}</div>`
      : `<pre class="json-view">${esc(resultTab === "json" ? json(result) : requestCode(lastRequest))}</pre>`;
}
function showError(container, message) {
  container.innerHTML = `<div class="result-error"><h3>这次决策没有完成</h3><p>${esc(message)}</p><a href="#about" class="secondary-button">查看模型启动说明 ${icon("arrow-right")}</a></div>`;
}
function saveRun(title, request, response, kind = "decision") {
  history.unshift({
    id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
    time: new Date().toISOString(),
    title,
    request,
    result: response,
    kind,
  });
  history = history.slice(0, 30);
  try {
    sessionStorage.setItem(historyKey, json(history));
  } catch {
    toast("浏览器存储不可用，记录仅保留在本次会话。");
  }
  $("#history-count").textContent = history.length;
}
async function runDecision() {
  if (
    !currentUser ||
    running ||
    guardRunning ||
    !selected ||
    $("#gpu-dialog").open
  )
    return;
  let body;
  try {
    body = collectRequest();
  } catch (e) {
    showError($("#results"), e.message);
    $(".result-panel").scrollIntoView({ block: "start", behavior: "smooth" });
    return;
  }
  running = true;
  $("#run-decision-label").textContent = "运行中…";
  $$(
    "#page-playground input, #page-playground textarea, #page-playground select, #page-playground button",
  ).forEach((el) => {
    el.disabled = true;
  });
  let stopTimer = () => {};
  try {
    if (body.mode === "live" && !(await ensureGpuReady("决策工作台"))) return;
    result = null;
    lastRequest = null;
    $(".result-panel").setAttribute("aria-busy", "true");
    $("#result-status").textContent =
      body.mode === "live" ? "推理中" : "读取示例";
    $("#results").innerHTML =
      `<div class="result-loading"><div class="spinner"></div><span>${body.mode === "live" ? "Decider 正在判断…" : "正在读取示例…"}</span></div>`;
    $(".result-panel").scrollIntoView({ block: "start", behavior: "smooth" });
    stopTimer = startRunTimer($("#results"));
    result = await api("/api/decide", body);
    lastRequest = body;
    $("#result-status").textContent =
      result.source === "live" ? "推理完成" : "示例回放";
    $("#result-status").className = "subtle-badge success";
    saveRun(selected.title, body, result);
    renderResults();
  } catch (e) {
    $("#result-status").textContent = "未完成";
    $("#result-status").className = "subtle-badge";
    showError($("#results"), e.message);
  } finally {
    stopTimer();
    running = false;
    $("#run-decision-label").textContent = "运行决策";
    $$(
      "#page-playground input, #page-playground textarea, #page-playground select, #page-playground button",
    ).forEach((el) => {
      el.disabled = false;
    });
    $("#add-question").disabled = questions.length >= 8;
    $$("[data-remove]").forEach((el) => {
      el.disabled = questions.length === 1;
    });
    $("#copy-result").disabled = !result;
    $(".result-panel").setAttribute("aria-busy", "false");
  }
}

function resetGuard() {
  guardResult = null;
  $("#guard-results").innerHTML =
    `<div class="empty-state compact"><div class="empty-icon">${icon("shield")}</div><h3>为工具调用加一道判断</h3><p>运行两个独立的问题，观察概率如何<br>转化为工作流中的下一步。</p></div>`;
}
async function runGuard() {
  if (!currentUser || guardRunning || running || $("#gpu-dialog").open) return;
  const body = {
    mode,
    measure_decisions: true,
    message: $("#guard-message").value,
    location: $("#guard-location").value,
    threshold: Number($("#guard-threshold").value),
  };
  if (!body.message.trim() || !body.location.trim()) {
    showError($("#guard-results"), "请填写用户请求和城市参数。");
    return;
  }
  guardRunning = true;
  $$("#page-guard input, #page-guard textarea, #page-guard button").forEach(
    (el) => {
      el.disabled = true;
    },
  );
  let stopTimer = () => {};
  try {
    if (body.mode === "live" && !(await ensureGpuReady("工具调用守卫"))) return;
    $("#guard-results").innerHTML =
      '<div class="result-loading"><div class="spinner"></div><span>正在检查参数依据与调用时机…</span></div>';
    stopTimer = startRunTimer($("#guard-results"));
    guardResult = await api("/api/guard", body);
    saveRun("工具调用守卫", body, guardResult, "guard");
    renderGuard();
  } catch (e) {
    showError($("#guard-results"), e.message);
  } finally {
    stopTimer();
    guardRunning = false;
    $$("#page-guard input, #page-guard textarea, #page-guard button").forEach(
      (el) => {
        el.disabled = false;
      },
    );
  }
}
function renderGuard() {
  if (!guardResult) return;
  const p = guardResult.policy;
  $("#guard-results").innerHTML = `${sourceBanner(guardResult)}
    ${renderAnswer("args_grounded", guardResult.answers.args_grounded, guardResult, "args_grounded · 参数有依据")}
    ${renderAnswer("premature", guardResult.answers.premature, guardResult, "premature · 调用过早")}
    <div class="guard-verdict ${p.action === "Proceed" ? "proceed" : ""}"><span class="verdict-label">POLICY DECISION · 阈值 ${p.threshold.toFixed(2)}</span><h3>${esc(p.action)}</h3><p>${esc(p.reason)}</p></div>
    <pre class="policy-code">if args_grounded &lt; ${p.threshold.toFixed(2)}:
    return Guide("请先向用户确认参数")
elif premature &gt;= ${p.threshold.toFixed(2)}:
    return Guide("请先补充必要信息")
else:
    return Proceed()</pre>
    <p class="input-hint">本演示未执行天气工具。${p.action === "Guide" ? "在 Agent 中，Guide 会让模型带着反馈继续下一轮。" : "在 Agent 中，Proceed 会允许这次工具调用继续。"}</p>
    ${metrics(guardResult)}`;
}
function renderHistory() {
  $("#history-count").textContent = history.length;
  $("#clear-history").disabled = history.length === 0;
  $("#history-list").innerHTML = history.length
    ? history
        .map(
          (item, i) => `<details class="history-row"><summary>
    <span>${icon(item.kind === "guard" ? "shield" : "route")}</span><div class="history-main"><strong>${esc(item.title)}</strong><p>${esc(item.request.state || item.request.message)}</p><small class="history-duration">总时间 ${duration(totalDuration(item.result))}</small></div>
    <span class="subtle-badge ${item.result.source === "live" ? "success" : ""}">${item.result.source === "live" ? "真实推理" : "示例回放"}</span>
    <span class="history-time">${esc(new Date(item.time).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }))}</span></summary>
    <div class="history-detail"><div class="history-timings">${Object.keys(
      item.result.answers || {},
    )
      .map(
        (key) =>
          `<div><span>${esc(key)}</span><strong>${decisionTiming(item.result, key)}</strong></div>`,
      )
      .join(
        "",
      )}</div><pre>${esc(json({ request: item.request, response: item.result }))}</pre><div class="history-actions"><button class="secondary-button" data-export="${i}">${icon("copy")}导出 JSON</button></div></div></details>`,
        )
        .join("")
    : `<div class="empty-state history-empty"><div class="empty-icon">${icon("history")}</div><h3>还没有运行记录</h3><p>回到工作台运行你的第一个决策。</p><a class="secondary-button" href="#playground" style="margin-top:20px">前往工作台 ${icon("arrow-right")}</a></div>`;
}
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext)
      await navigator.clipboard.writeText(text);
    else {
      const input = document.createElement("textarea");
      input.value = text;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.append(input);
      input.select();
      const copied = document.execCommand("copy");
      input.remove();
      if (!copied) throw new Error("Clipboard unavailable");
    }
    toast("已复制到剪贴板");
  } catch {
    toast("浏览器不允许访问剪贴板，请在 JSON 视图中手动复制。");
  }
}

document.addEventListener("click", (e) => {
  const category = e.target.closest("[data-category]");
  if (category && !running) {
    scenarioCategory = category.dataset.category;
    renderScenarios();
    $$("#scenario-filters button")
      .find((button) => button.dataset.category === scenarioCategory)
      ?.focus();
  }
  if (e.target.closest("#clear-scenario-filters")) {
    scenarioCategory = "all";
    $("#scenario-search").value = "";
    renderScenarios();
    $("#scenario-search").focus();
  }
  const modeButton = e.target.closest("[data-mode]");
  if (modeButton) setMode(modeButton.dataset.mode);
  const scenario = e.target.closest("[data-example]");
  if (scenario) selectExample(scenario.dataset.example);
  const remove = e.target.closest("[data-remove]");
  if (remove && questions.length > 1 && !running) {
    questions.splice(Number(remove.dataset.remove), 1);
    renderQuestions();
    invalidate();
  }
  const tab = e.target.closest("[data-result-tab]");
  if (tab && !running) {
    resultTab = tab.dataset.resultTab;
    $$("[data-result-tab]").forEach((el) => {
      el.classList.toggle("active", el === tab);
      el.setAttribute("aria-selected", String(el === tab));
    });
    renderResults();
  }
  const preset = e.target.closest("[data-guard-preset]");
  if (preset && !guardRunning) {
    $("#guard-message").value =
      preset.dataset.guardPreset === "missing"
        ? "What's the weather?"
        : "What's the weather in Seattle?";
    $("#guard-location").value = "Seattle";
    $$("[data-guard-preset]").forEach((el) => {
      el.classList.toggle("active", el === preset);
      el.setAttribute("aria-pressed", String(el === preset));
    });
    resetGuard();
  }
  const exportButton = e.target.closest("[data-export]");
  if (exportButton) {
    const item = history[Number(exportButton.dataset.export)];
    const url = URL.createObjectURL(
      new Blob([json(item)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `decider-${item.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
});
$("#scenario-search").addEventListener("input", renderScenarios);
$("#questions").addEventListener("input", (e) => {
  const card = e.target.closest("[data-question]");
  if (!card || running) return;
  const q = questions[Number(card.dataset.question)];
  if (e.target.dataset.edit === "instructions") q.instructions = e.target.value;
  if (e.target.dataset.edit === "criteria") q.criteriaDraft = e.target.value;
  invalidate();
});
$("#questions").addEventListener("change", (e) => {
  if (e.target.dataset.edit !== "type" || running) return;
  const q =
    questions[Number(e.target.closest("[data-question]").dataset.question)];
  q.type = e.target.value;
  q.criteria = criteriaFor(q.type);
  delete q.criteriaDraft;
  renderQuestions();
  invalidate();
});
$("#add-question").addEventListener("click", () => {
  if (questions.length >= 8 || running) return;
  let i = questions.length + 1;
  while (questions.some((q) => q.id === `question_${i}`)) i++;
  questions.push({
    id: `question_${i}`,
    type: "noul",
    instructions: "Does this request need human review?",
  });
  renderQuestions();
  invalidate();
  $("#questions .question-card:last-child .question-instructions").focus();
});
$("#state-input").addEventListener("input", () => {
  countChars();
  invalidate();
});
$("#reset-example").addEventListener("click", () => {
  if (selected) selectExample(selected.id);
});
$("#run-decision").addEventListener("click", runDecision);
$("#edit-decision").addEventListener("click", () => {
  $(".input-panel").scrollIntoView({ block: "start", behavior: "smooth" });
  $("#state-input").focus({ preventScroll: true });
});
$("#run-guard").addEventListener("click", runGuard);
$("#refresh-connection").addEventListener("click", checkConnection);
$("#gpu-open").addEventListener("click", () => openGpuDialog());
$("#gpu-close").addEventListener("click", () => $("#gpu-dialog").close());
$("#gpu-return").addEventListener("click", () => $("#gpu-dialog").close());
$("#gpu-refresh").addEventListener("click", checkGpu);
$("#gpu-start").addEventListener("click", () => changeGpu("start"));
$("#gpu-stop").addEventListener("click", () => changeGpu("stop"));
setInterval(() => {
  if (
    !document.hidden &&
    ($("#gpu-dialog").open ||
      ["starting", "stopping"].includes(gpuState?.phase))
  )
    checkGpu();
}, 5000);
$("#copy-result").addEventListener("click", () => {
  if (result)
    copyText(resultTab === "request" ? requestCode(lastRequest) : json(result));
});
$("#guard-threshold").addEventListener("input", (e) => {
  $("#threshold-value").value = Number(e.target.value).toFixed(2);
  if (guardResult) resetGuard();
});
["#guard-message", "#guard-location"].forEach((s) =>
  $(s).addEventListener("input", () => {
    $$("[data-guard-preset]").forEach((el) => {
      el.classList.remove("active");
      el.setAttribute("aria-pressed", "false");
    });
    resetGuard();
  }),
);
$("#clear-history").addEventListener("click", () => {
  history = [];
  try {
    sessionStorage.removeItem(historyKey);
  } catch {
    /* Session-only history. */
  }
  renderHistory();
  toast("运行记录已清空");
});
window.addEventListener("hashchange", showPage);
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    if ($("#gpu-dialog").open) return;
    if (currentPage === "playground") runDecision();
    else if (currentPage === "guard") runGuard();
  }
});
hydrateIcons();
async function initializeWorkspace(user) {
  currentUser = user;
  historyKey = `decider-history-v2:${user.username}`;
  try {
    // Remove legacy history shared between all users of the same browser.
    localStorage.removeItem("decider-history-v1");
    const saved = JSON.parse(sessionStorage.getItem(historyKey) || "[]");
    if (Array.isArray(saved))
      history = saved
        .filter(
          (x) => x && x.request && x.result && typeof x.title === "string",
        )
        .slice(0, 30);
  } catch {
    /* History can remain in memory. */
  }
  $("#account-name").textContent = user.username;
  $(".avatar").textContent = user.username[0].toUpperCase();
  $("#login-page").hidden = true;
  document.body.classList.remove("auth-pending");
  showPage();
  $("#history-count").textContent = history.length;
  checkConnection();
  checkGpu();
  try {
    examples = await api("/api/examples");
    renderScenarios();
    selectExample(examples[0].id);
  } catch (e) {
    $("#scenarios").innerHTML =
      `<div class="result-error"><h3>场景加载失败</h3><p>${esc(e.message)}</p><button class="secondary-button" id="retry-load">重新加载</button></div>`;
    $("#retry-load").addEventListener("click", () => location.reload());
    $("#run-decision").disabled = true;
  }
}

function loginError(message) {
  $("#login-error").textContent = message;
  $("#login-error").hidden = !message;
}
function loginBusy(busy, checking = false) {
  $("#login-submit").disabled = busy;
  $("#login-submit > span").textContent = checking
    ? "正在检查登录状态…"
    : busy
      ? "正在登录…"
      : "登录工作空间";
  $("#login-username").disabled = busy;
  $("#login-password").disabled = busy;
}
$("#toggle-password").addEventListener("click", () => {
  const show = $("#login-password").type === "password";
  $("#login-password").type = show ? "text" : "password";
  $("#toggle-password").textContent = show ? "隐藏" : "显示";
  $("#toggle-password").setAttribute(
    "aria-label",
    show ? "隐藏密码" : "显示密码",
  );
  $("#toggle-password").setAttribute("aria-pressed", String(show));
});
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const credentials = {
    username: $("#login-username").value.trim(),
    password: $("#login-password").value,
  };
  loginBusy(true);
  loginError("");
  try {
    const user = await api("/api/auth/login", credentials);
    $("#login-password").value = "";
    await initializeWorkspace(user);
  } catch (error) {
    loginError(error.message);
    loginBusy(false);
    $("#login-password").focus();
  }
});
$("#logout-button").addEventListener("click", async () => {
  $("#gpu-dialog").close();
  $("#logout-button").disabled = true;
  try {
    await api("/api/auth/logout", {});
    try {
      sessionStorage.removeItem(historyKey);
      localStorage.setItem("decider-logout", String(Date.now()));
    } catch {
      /* Storage is optional. */
    }
    document.body.classList.add("auth-pending");
    location.reload();
  } catch (error) {
    toast(error.message);
    $("#logout-button").disabled = false;
  }
});
window.addEventListener("storage", (event) => {
  if (event.key === "decider-logout" && currentUser) {
    $("#gpu-dialog").close();
    try {
      sessionStorage.removeItem(historyKey);
    } catch {
      /* Storage is optional. */
    }
    document.body.classList.add("auth-pending");
    location.reload();
  }
});
try {
  const response = await fetch("/api/auth/me", {
    credentials: "same-origin",
    cache: "no-store",
    signal: AbortSignal.timeout(7000),
  });
  if (response.ok) {
    await initializeWorkspace(await response.json());
  } else {
    if (response.status !== 401) loginError("登录服务暂时不可用，请稍后重试。");
    loginBusy(false);
    $("#login-username").focus();
  }
} catch {
  loginError("无法连接登录服务，请检查网络后重试。");
  loginBusy(false);
}
