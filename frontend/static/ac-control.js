let ui, root, catalog, job = null, caseId = "S01", field = "t_power";
let dataset = "spec", category = "all", mode = "full30", order = "original";
let owner = null, generation = 0, loading = false, busy = false, polling = false, error = "";
const opened = new Set();
const layouts = {single: "单步决策", serial30: "30 步串行", full30: "一次全答", all: "三种方式对比"};
const phases = {queued: "等待轮次", running: "正在决策", done: "已完成", error: "调用失败", cancelled: "已取消"};
const verdicts = {correct: "选对", extra: "多发", missing: "漏发", wrong_value: "错值", unanswered: "未返回"};
const historical = {
  liquid_lora: ["90%", "0.657 秒", "2026-11-01 · LoRA", "LIQUID_AC_LORA_RESULTS.md"],
  jev: ["95%", "0.097 秒", "2026-10-31 · 原始输入", "AC_ALL_MODELS_INPUT_OPTIMIZATION_RESULTS.md"],
  gpt: ["100%", "2.449 秒", "2026-10-31 · 原始输入", "AC_ALL_MODELS_INPUT_OPTIMIZATION_RESULTS.md"],
};
const esc = (v) => ui.esc(String(v ?? ""));
const ms = (v) => v == null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(3)} 秒` : `${v.toFixed(1)} ms`;
const current = () => catalog.cases.find(c => c.id === caseId);
const visibleCases = () => catalog.cases.filter(c => c.dataset === dataset && (category === "all" || c.category === category));
const lock = () => busy ? "disabled" : "";
const savedKey = () => `ac-control-v1-${owner}`;
const details = (key, title, data) => `<details data-ac-detail="${esc(key)}" ${opened.has(key) ? "open" : ""}><summary>${esc(title)}</summary><pre>${esc(typeof data === "string" ? data : JSON.stringify(data, null, 2))}</pre></details>`;
const caption = (key, value) => value === "omit" ? "保持不变（omit）" : value == null ? "未返回" : `${value} · ${catalog.template.questions[key].criteria[value] || ""}`;

function payload(c = current()) {
  const p = structuredClone(catalog.template);
  const state = JSON.parse(p.state); state.query = c.query; p.state = JSON.stringify(state);
  return p;
}

// JavaScript sorts integer-like object keys. Preserve the server's explicit
// order for the candidate display and the exact serialized request instead.
function candidateIds(key) {
  const ids = [...catalog.candidate_orders[key]];
  return order === "reversed" ? ids.reverse() : ids;
}

function payloadText(c = current()) {
  const p = payload(c);
  const questions = Object.entries(p.questions).map(([key, q]) =>
    `${JSON.stringify(key)}:{"type":${JSON.stringify(q.type)},"instructions":${JSON.stringify(q.instructions)},"criteria":{${candidateIds(key).map(id => `${JSON.stringify(id)}:${JSON.stringify(q.criteria[id])}`).join(",")}}}`);
  return `{"state":${JSON.stringify(p.state)},"questions":{${questions.join(",")}}}`;
}

function select(id) {
  caseId = id;
  field = current().expected[0]?.cmdKey || "t_power";
  job = null; error = ""; opened.clear();
  sessionStorage.removeItem(savedKey());
}

export async function mountACControl(helpers) {
  ui = helpers;
  const nextOwner = helpers.user.username;
  if (owner !== nextOwner) {
    owner = nextOwner; generation++; catalog = null; job = null; polling = false; loading = false;
    opened.clear();
  }
  if (catalog || loading) return;
  const mine = generation;
  loading = true; job = null; busy = false; error = "";
  root = document.querySelector("#ac-control-workspace");
  try {
    const nextCatalog = await ui.api("/api/ac-control/catalog");
    if (mine !== generation) return;
    catalog = nextCatalog;
    root.onclick = click;
    root.onchange = change;
    root.addEventListener("toggle", e => {
      if (e.target.dataset.acDetail) e.target.open ? opened.add(e.target.dataset.acDetail) : opened.delete(e.target.dataset.acDetail);
    }, true);
    const saved = sessionStorage.getItem(savedKey());
    if (saved) {
      try {
        const restored = await ui.api(`/api/ac-control/runs/${encodeURIComponent(saved)}`);
        if (mine !== generation) return;
        job = restored;
        caseId = job.config.case_ids[0]; mode = job.config.mode; order = job.config.order; field = job.config.field;
        dataset = current().dataset; category = "all"; busy = job.status === "running";
      } catch { if (mine !== generation) return; sessionStorage.removeItem(savedKey()); }
    }
    render();
    if (busy) poll();
  } catch (e) {
    if (mine !== generation) return;
    catalog = null;
    root.innerHTML = `<div class="ac-error" role="alert">${esc(e.message)} <button data-ac-reload>重试加载</button></div>`;
    root.onclick = () => mountACControl(helpers);
  } finally { if (mine === generation) loading = false; }
}

function render() {
  const c = current(), p = payload();
  const refs = Object.fromEntries(c.expected.map(v => [v.cmdKey, String(v.cmdValue)]));
  const selectedQuestion = p.questions[field];
  const relevant = job?.records.filter(r => r.case_id === caseId) || [];
  root.innerHTML = `
    <div class="ac-heading"><div><span class="ac-eyebrow">AIR CONDITIONER · LIVE COMPARISON</span>
      <h1>一句指令，三个模型怎么选？</h1><p>Liquid LoRA、Jev 与 GPT 使用相同的空调能力、问题和选项，逐项比较真实选择。</p></div>
      <span class="ac-pill">30 项能力 · 283 个候选</span></div>
    <details class="ac-history"><summary>历史实测参考 · 一次全答</summary><div class="ac-reference-grid">
      ${catalog.providers.map(v => { const h = historical[v.id]; return `<article><strong>${esc(v.name)}</strong><b>${h[0]} <small>/ ${h[1]}</small></b><span>${h[2]}</span><a href="https://github.com/milan9527/StrandsDecider/blob/main/docs/${h[3]}" target="_blank" rel="noreferrer">查看实测报告 ↗</a></article>`; }).join("")}
      </div><p>历史数据来自不同轮次的原规范 20 题三轮测试，不是下方的实时结果。准确率按完整命令集合严格匹配。</p></details>
    <section class="ac-controls" aria-label="空调场景与运行方式">
      <div class="ac-select-row"><label>场景集合<select data-ac-dataset ${lock()}>
        ${Object.entries({spec:"原规范 · 20 题",chinese:"中文表达 · 24 题",validation:"英文改写 · 24 题",extension:"扩展诊断 · 10 题"}).map(([k,v])=>`<option value="${k}" ${dataset===k?"selected":""}>${v}</option>`).join("")}</select></label>
        <label>指令类型<select data-ac-category ${lock()}><option value="all">全部</option><option value="single" ${category==="single"?"selected":""}>单指令</option><option value="multi" ${category==="multi"?"selected":""}>多指令（多个设置）</option></select></label>
        <label class="ac-case-select">选择场景<select data-ac-case ${lock()}>${visibleCases().map(v=>`<option value="${v.id}" ${caseId===v.id?"selected":""}>${v.id} · ${esc(v.title || v.query)}</option>`).join("")}</select></label></div>
      <div class="ac-query"><span>${c.category==="single"?"单指令":"多指令"} · ${esc(c.id)}</span><h2>${esc(c.query)}</h2>
        <div class="ac-command-tags">${c.expected.length ? c.expected.map(v=>`<span>${esc(catalog.fields[v.cmdKey])} <b>${esc(v.cmdValue)}</b></span>`).join("") : '<span>所有字段保持不变</span>'}</div>
        <p>上方是参考命令；其余字段应选 omit。关闭值 0 也是实际命令。演示展示命令，不操作真实空调。</p></div>
      <div class="ac-modes" role="group" aria-label="调用方式">${Object.entries(layouts).map(([k,v])=>`<button data-ac-mode="${k}" aria-pressed="${mode===k}" class="${mode===k?"active":""}" ${lock()}>${v}</button>`).join("")}</div>
      <p class="ac-explain">${mode==="single"?"单步只请求下方选定的一个字段，仅评价该字段。":mode==="serial30"?"同一条用户指令，依次发出 30 次单字段请求；上一字段的答案不会传给下一字段。":mode==="full30"?"一次请求携带全部 30 个问题，比较最终命令集合是否完全正确。":"分别实测一个字段、30 步串行和一次全答；三种方式按各自实际请求计时。"}</p>
      <div class="ac-select-row"><label>${mode==="single"||mode==="all"?"单步字段 / 查看选项":"查看字段选项"}<select data-ac-field ${lock()}>${Object.entries(catalog.fields).map(([k,v])=>`<option value="${k}" ${field===k?"selected":""}>${esc(v)} · ${k}</option>`).join("")}</select></label>
        <label>选项顺序<select data-ac-order ${lock()}><option value="original">原顺序</option><option value="reversed" ${order==="reversed"?"selected":""}>倒序对照</option></select></label></div>
      <details class="ac-options" data-ac-detail="options" ${opened.has("options")?"open":""}><summary>${esc(catalog.fields[field])}：完整问题与 ${Object.keys(selectedQuestion.criteria).length} 个选项</summary>
        <p>${esc(selectedQuestion.instructions)}</p><div class="ac-option-grid">${candidateIds(field).map(key=>`<div class="${key===(refs[field]||"omit")?"expected":""}"><b>${esc(key)}</b><span>${esc(selectedQuestion.criteria[key])}</span>${key===(refs[field]||"omit")?"<em>参考选择</em>":""}</div>`).join("")}</div></details>
      <div class="ac-actions"><button class="primary-button" data-ac-run ${lock()}>开始三模型对比</button><button class="secondary-button" data-ac-batch ${lock()}>运行全部规范场景（20 条）</button>
        ${busy?`<button class="secondary-button" data-ac-cancel ${job?.cancel_requested?"disabled":""}>${job?.cancel_requested?"等待当前请求结束":"取消后续请求"}</button>`:""}
        <button class="text-button" data-ac-export ${!job?"disabled":""}>导出本轮 JSON</button></div>
      <div class="ac-service-status">${catalog.providers.map(v=>`<span class="${catalog.configured[v.id]?"":"unavailable"}">${esc(v.name)} · ${catalog.configured[v.id]?"已配置":"未配置"}</span>`).join("")}</div>
    </section>
    ${error?`<div class="ac-error" role="alert">${esc(error)} ${busy&&!polling?'<button data-ac-resume>继续查询</button>':""}</div>`:""}
    <div class="ac-run-status" role="status">${job ? `实时运行 · ${phases[job.status]} · 已结束 ${job.completed}/${job.total} 个模型任务 · 本轮等待 ${ms(job.elapsed_ms)}` : "等待运行 · 三个模型按顺序调用，历史成绩不会填入实时结果。"}</div>
    ${job?.config.case_ids.length>1?`<div class="ac-batch-nav" aria-label="本轮场景">${job.config.case_ids.map(id=>`<button data-ac-inspect="${id}" class="${caseId===id?"active":""}">${id}</button>`).join("")}</div>`:""}
    <div class="ac-results">${catalog.providers.map(v=>modelCard(v,relevant)).join("")}</div>
    ${job?`<details class="ac-audit"><summary>本轮汇总与计时口径</summary>${batchSummary()}<p>单步正确率按字段统计；串行与全答按整条命令集合统计。请求失败单列，未返回字段不会补为 omit。任务耗时包括模型请求、网络及服务端等待，可能不同于历史独占 GPU 测试；本轮等待还包括其他模型的轮次。取消的任务不计入正确率。无自动重试或答案修复。</p></details>`:""}
    ${details("shared-input","完整业务输入（参考答案不发送给模型）",payloadText())}`;
}

function modelCard(provider, records) {
  const own = records.filter(r=>r.provider===provider.id);
  return `<article class="ac-model ${provider.id}"><header><span>${esc(provider.detail)}</span><h2>${esc(provider.name)}</h2></header>
    ${own.length?own.map(r=>{
      const s=r.score, ended=r.status==="done", ok=ended&&s?.correct;
      return `<section class="ac-layout"><div class="ac-layout-title"><strong>${layouts[r.layout]}</strong><span class="ac-state ${r.status==="running"?"running":ended?(ok?"good":"bad"):r.status}">${ended?(ok?"完全正确":"选择有误"):phases[r.status]}</span></div>
        <div class="ac-time">${ms(r.elapsed_ms)}<small>${r.layout==="single"?"单字段往返":"完整任务耗时"}</small></div>
        <p>${s?`字段符合参考 ${s.matched}/${s.total}`:`已返回 ${r.calls.filter(c=>c.status==="ok").length} 次请求`}${r.model?` · ${esc(r.model)}`:""}</p>
        <div class="ac-choices">${Object.entries(r.choices).filter(([,v])=>v!=="omit").map(([k,v])=>`<span class="${s?.fields[k]==="correct"?"":"wrong"}">${esc(catalog.fields[k])} <b>${esc(v)}</b></span>`).join("")||`<span>${r.calls.some(c=>c.status==="ok")?"已返回字段均为 omit":"尚未返回命令"}</span>`}</div>
        ${r.calls.filter(c=>c.status==="error").map(c=>`<p class="ac-error">${esc(c.error)}</p>`).join("")}
        <details data-ac-detail="${provider.id}-${r.layout}" ${opened.has(`${provider.id}-${r.layout}`)?"open":""}><summary>逐字段选择、参考答案与请求耗时</summary>
          <div class="ac-field-list">${Object.keys(r.expected||{}).map(k=>{
            const call=r.calls.find(c=>c.keys.includes(k));
            return `<div class="ac-field ${s?.fields[k]||""}"><strong>${esc(catalog.fields[k])}<code>${k}</code></strong><span>模型：${esc(caption(k,r.choices[k]))}</span><span>参考：${esc(caption(k,r.expected[k]))}</span><small>${verdicts[s?.fields[k]]||"等待"} · ${call?ms(call.elapsed_ms):"—"}${r.layout==="full30"?"（整请求）":""}</small></div>`;
          }).join("")}</div></details>
        ${details(`${provider.id}-${r.layout}-raw`,"实际响应与输入哈希",r.calls)}
      </section>`;
    }).join(""):'<div class="ac-empty">选择场景并运行，查看真实决策。</div>'}</article>`;
}

function batchSummary() {
  return `<div class="ac-table-wrap"><table><thead><tr><th>模型 / 方式</th><th>正确 / 已完成</th><th>接口失败</th><th>平均任务耗时</th></tr></thead><tbody>${catalog.providers.flatMap(p=>Object.keys(layouts).filter(l=>l!=="all").map(l=>{
    const rows=job.records.filter(r=>r.provider===p.id&&r.layout===l&&["done","error"].includes(r.status));
    if(!rows.length)return "";
    return `<tr><td>${esc(p.name)} · ${layouts[l]}</td><td>${rows.filter(r=>r.status==="done"&&r.score.correct).length}/${rows.length}</td><td>${rows.filter(r=>r.status==="error").length}</td><td>${ms(rows.reduce((s,r)=>s+r.elapsed_ms,0)/rows.length)}</td></tr>`;
  })).join("")}</tbody></table></div>`;
}

async function start(batch=false) {
  if(busy)return;
  const mine=generation;
  busy=true; error=""; job=null; opened.clear(); render();
  try {
    const ids=batch?catalog.cases.filter(c=>c.dataset==="spec").map(c=>c.id):[caseId];
    const started=await ui.api("/api/ac-control/runs",{case_ids:ids,mode,field,order});
    if(mine!==generation)return;
    job=started;
    caseId=ids[0]; dataset=current().dataset; category="all";
    sessionStorage.setItem(savedKey(),job.id); render(); await poll();
  } catch(e) { if(mine!==generation)return; error=e.message; busy=false; render(); }
}

async function poll() {
  if(polling||!job)return;
  polling=true;const mine=generation, runId=job.id;let failures=0;
  try {
    while(job.status==="running"&&mine===generation) {
      await new Promise(r=>setTimeout(r,1000));
      if(mine!==generation)return;
      try {
        const latest=await ui.api(`/api/ac-control/runs/${encodeURIComponent(runId)}`);
        if(mine!==generation)return;
        job=latest;busy=job.status==="running";error="";failures=0;render();
      } catch(e) {
        if([401,404].includes(e.status)||++failures>=3) { error="结果查询中断。已提交的模型请求不会重复执行。";break; }
      }
    }
  } finally { if(mine===generation){polling=false;render();} }
}

function change(e) {
  if(busy)return;
  if(e.target.matches("[data-ac-dataset]")) {dataset=e.target.value;category="all";select(visibleCases()[0].id);}
  if(e.target.matches("[data-ac-category]")) {category=e.target.value;select(visibleCases()[0].id);}
  if(e.target.matches("[data-ac-case]"))select(e.target.value);
  if(e.target.matches("[data-ac-field]")) {field=e.target.value;if(mode==="single"||mode==="all")job=null;}
  if(e.target.matches("[data-ac-order]")) {order=e.target.value;job=null;}
  if(!job)sessionStorage.removeItem(savedKey());
  render();
}

async function click(e) {
  const b=e.target.closest("button");if(!b)return;
  if(b.hasAttribute("data-ac-run"))start();
  if(b.hasAttribute("data-ac-batch"))start(true);
  if(b.dataset.acMode&&!busy) {mode=b.dataset.acMode;job=null;sessionStorage.removeItem(savedKey());render();}
  if(b.dataset.acInspect) {caseId=b.dataset.acInspect;render();}
  if(b.hasAttribute("data-ac-resume"))poll();
  if(b.hasAttribute("data-ac-cancel")&&job) {
    const mine=generation;
    try {const cancelled=await ui.api(`/api/ac-control/runs/${encodeURIComponent(job.id)}/cancel`,{});if(mine!==generation)return;job=cancelled;render();}
    catch(e){if(mine!==generation)return;error=e.message;render();}
  }
  if(b.hasAttribute("data-ac-export")&&job) {
    const result={...job,model_inputs:Object.fromEntries(job.config.case_ids.map(id=>[id,payload(catalog.cases.find(c=>c.id===id))])),
      model_input_json:Object.fromEntries(job.config.case_ids.map(id=>[id,payloadText(catalog.cases.find(c=>c.id===id))]))};
    const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));
    const a=document.createElement("a");a.href=url;a.download=`ac-control-${job.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
}
