// SDA-LLM live dialogue page. Talks only to the local server (same origin); the API key never reaches this page.
"use strict";

const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const S = { meta: null, progress: null, mode: "experiment", q: null, session: null, demoSet: "chair", busy: false };

function store(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } }
function load(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } }

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || r.statusText), { status: r.status });
  return data;
}

// ------------------------------------------------------------------ images and boxes
function imageSet() {
  if (S.mode === "demo") return S.demoSet;
  const q = S.meta.questions.find((x) => x.q === S.q);
  return q ? q.image_set : "chair";
}

function buildGrid() {
  const grid = $("grid");
  grid.innerHTML = "";
  S.meta.views.forEach((v, i) => {
    const card = document.createElement("div");
    card.className = "view";
    card.dataset.view = i;
    card.innerHTML = `<img alt="view ${i}"><svg viewBox="0 0 ${v.w} ${v.h}" preserveAspectRatio="none"></svg>` +
      `<span class="cap">view ${i} · ${v.heading}°</span>`;
    card.addEventListener("click", () => zoom(i));
    grid.appendChild(card);
  });
}

function highlights() {
  // ids to light up: candidates of the latest round, the final answer, the target (if shown)
  const s = S.session;
  const out = { cand: new Set(), final: new Set(), target: new Set() };
  if (!s) return out;
  const last = s.turns[s.turns.length - 1];
  if (s.ended && s.end && s.end.reason === "single" && last) last.ids.forEach((i) => out.final.add(i));
  else if (last) last.ids.forEach((i) => out.cand.add(i));
  if (S.mode === "experiment" && $("show-target").checked && s.target_tag) {
    const t = S.meta.boxes.all.flat().find((b) => b.tag === s.target_tag);
    if (t) out.target.add(t.id);
  }
  return out;
}

function drawBoxes(svg, view, set, hl) {
  svg.innerHTML = "";
  let any = null;
  for (const b of S.meta.boxes[set][view]) {
    const kind = hl.final.has(b.id) ? "final" : hl.cand.has(b.id) ? "cand" : null;
    if (hl.target.has(b.id)) svg.appendChild(rect(b.box, "target"));
    if (!kind) continue;
    any = any === "final" ? "final" : kind;
    svg.appendChild(rect(b.box, kind));
    const t = document.createElementNS(SVGNS, "text");
    // below the box, so the tag drawn on the image stays readable (above it if the box reaches the bottom)
    const h = S.meta.views[view].h, below = b.box[3] + 40 <= h;
    t.setAttribute("x", b.box[0] + 4); t.setAttribute("y", below ? b.box[3] + 38 : b.box[1] - 10);
    t.setAttribute("class", "lbl " + kind); t.textContent = b.tag;
    svg.appendChild(t);
  }
  return any;
}

function rect(b, cls) {
  const r = document.createElementNS(SVGNS, "rect");
  r.setAttribute("x", b[0]); r.setAttribute("y", b[1]);
  r.setAttribute("width", b[2] - b[0]); r.setAttribute("height", b[3] - b[1]);
  r.setAttribute("class", cls);
  return r;
}

function renderViews() {
  const set = imageSet(), hl = highlights();
  document.querySelectorAll(".view").forEach((card) => {
    const i = +card.dataset.view, img = card.querySelector("img");
    const src = `/img/${set}/${i}.jpg`;
    if (img.getAttribute("src") !== src) img.setAttribute("src", src);
    const lit = drawBoxes(card.querySelector("svg"), i, set, hl);
    card.classList.toggle("lit", lit === "cand");
    card.classList.toggle("lit-final", lit === "final");
  });
}

function zoom(i) {
  const v = S.meta.views[i], set = imageSet();
  const box = $("zoom-inner");
  box.innerHTML = `<img src="/img/${set}/${i}.jpg" alt="view ${i}"><svg viewBox="0 0 ${v.w} ${v.h}" preserveAspectRatio="none"></svg>`;
  drawBoxes(box.querySelector("svg"), i, set, highlights());
  $("zoom").showModal();
}

// ------------------------------------------------------------------ progress, usage, chat
function renderProgress() {
  const ol = $("progress");
  ol.innerHTML = "";
  for (const p of S.progress.questions) {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.className = `chip ${p.status}` + (S.mode === "experiment" && p.q === S.q ? " current" : "");
    b.dataset.q = p.q;
    b.title = { todo: "未開始", active: "進行中", found: "找到", missed: "沒找到" }[p.status];
    b.innerHTML = `<b>${p.q}</b><small>${p.rounds} 輪</small>`;
    b.addEventListener("click", () => openQuestion(p.q, 0));
    li.appendChild(b);
    ol.appendChild(li);
  }
  const u = S.mode === "demo" ? S.progress.demo_usage : S.progress.usage;
  const sm = S.progress.summary;
  $("usage").textContent = `${S.mode === "demo" ? "展示" : "實驗"} tokens 輸入 ${u.input.toLocaleString()} · 輸出 ${u.output.toLocaleString()}` +
    ` · 快取讀 ${u.cache_read.toLocaleString()} · 快取寫 ${u.cache_write.toLocaleString()} · 約 US$${u.usd.toFixed(3)}` +
    (sm.finished && S.mode === "experiment" ? `　｜　已完成 ${sm.finished} 題，找到 ${(sm.found * 100).toFixed(0)}%，平均 ${sm.mean_rounds.toFixed(2)} 輪` : "");
}

function esc(t) { return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function renderChat() {
  const s = S.session, head = $("qhead"), log = $("log"), end = $("endnote");
  log.innerHTML = "";
  if (!s) {
    head.innerHTML = S.mode === "demo" ? "<h2>展示模式</h2><p>選圖組後按「新對話」。</p>" : "<h2>請從上方選一題</h2>";
    end.hidden = true;
    setInputs(false);
    return;
  }
  if (S.mode === "experiment") {
    const show = $("show-target").checked;
    head.innerHTML = `<h2>${s.q}　<span class="tgt">${show ? "正解 " + esc(s.target_tag) + (s.author_tag !== s.target_tag ? `（作者編號 ${esc(s.author_tag)}）` : "") : ""}</span></h2>` +
      `<p>答案檔有 ${s.n_sentences} 句，第一句自動送出。之後只能描述看得到的特徵。紀錄寫進 <code>${esc(S.meta.records)}</code></p>`;
  } else {
    head.innerHTML = `<h2>展示　${esc(s.dialogue_id)}</h2><p>圖組 ${{ chair: "椅子", whiteboard: "白板", all: "全部類別" }[s.image_set]}，不檢查輸入規則。</p>`;
  }
  for (const t of s.turns) {
    const me = document.createElement("li");
    me.className = "msg me";
    me.innerHTML = `<span class="who">我${t.auto ? "（答案檔第一句，自動送出）" : ""}　第 ${t.round} 輪</span>${esc(t.user)}`;
    log.appendChild(me);
    const ai = document.createElement("li");
    const fin = s.ended && s.end.reason === "single" && t.round === s.turns.length;
    ai.className = "msg ai";
    ai.innerHTML = `<span class="who">${esc(S.meta.model)}</span>` +
      `<div class="cands${fin ? " final" : ""}">${t.candidates.map((c) => `<span>${esc(c)}</span>`).join("") || "<em>沒有候選</em>"}</div>` +
      `<div class="reason">${esc(t.reason || "")}</div>`;
    log.appendChild(ai);
  }
  log.scrollTop = log.scrollHeight;
  if (s.ended) {
    const e = s.end, why = { single: "模型只回一個 ID", ee: "我輸入 ee 結束", max_round: "超過 10 輪" }[e.reason];
    end.hidden = false;
    end.className = "endnote" + (e.found === true ? " found" : e.found === false ? " missed" : "");
    end.innerHTML = `結束（${why}），共 ${e.rounds} 輪，最後答案 ${e.final.map(esc).join("、") || "無"}` +
      (e.found === undefined || e.found === null ? "" : (e.found ? "，<b>找到</b>" : "，<b>沒找到</b>") +
        ($("show-target").checked ? `（正解 ${esc(s.target_tag)}）` : ""));
  } else end.hidden = true;
  setInputs(!s.ended);
}

function setInputs(on) {
  const fresh = S.mode === "experiment" && S.session && !S.session.ended && S.session.turns.length === 0;
  $("start").hidden = !fresh;
  $("start").disabled = S.busy;
  if (fresh) on = false;
  $("input").disabled = !on || S.busy;
  $("send").disabled = !on || S.busy;
  $("ee").disabled = !on || S.busy;
  $("next").disabled = S.mode !== "experiment" || S.busy;
}

function render() { renderProgress(); renderChat(); renderViews(); }

function busy(on) {
  S.busy = on;
  document.body.classList.toggle("busy-cursor", on);
  $("form").classList.toggle("busy", on);
  setInputs(S.session && !S.session.ended);
}

async function run(fn) {
  busy(true);
  $("err").textContent = "";
  try {
    const d = await fn();
    if (d.session) S.session = d.session;
    if (d.progress) S.progress = d.progress;
  } catch (e) {
    $("err").textContent = e.status === 422 ? e.message : `錯誤：${e.message}`;
  } finally {
    busy(false);
    render();
  }
}

// ------------------------------------------------------------------ actions
function openQuestion(q, start = 0) {
  // showing a question is free; the first sentence (a paid call) is sent only by the start button
  if (S.mode !== "experiment") switchMode("experiment");
  S.q = q;
  store("live.q", q);
  return run(() => api(`/api/q/${q}/open?start=${start}`, {}));
}

async function send(text) {
  if (S.mode === "demo") return run(() => api("/api/demo/send", { text }));
  const c = await api("/api/check", { text });
  if (c.reason) { $("err").textContent = c.reason; return; }
  return run(() => api(`/api/q/${S.q}/send`, { text }));
}

function nextQuestion() {
  const qs = S.progress.questions, i = qs.findIndex((p) => p.q === S.q);
  const nxt = qs.slice(i + 1).concat(qs.slice(0, i + 1)).find((p) => p.status === "todo" || p.status === "active");
  if (nxt) openQuestion(nxt.q, 0);
  else $("err").textContent = "15 題都已結束。";
}

function switchMode(m) {
  S.mode = m;
  $("tab-exp").classList.toggle("active", m === "experiment");
  $("tab-demo").classList.toggle("active", m === "demo");
  $("tab-exp").setAttribute("aria-selected", m === "experiment");
  $("tab-demo").setAttribute("aria-selected", m === "demo");
  $("demo-bar").hidden = m !== "demo";
  $("progress-bar").classList.toggle("dim", m === "demo");
  S.session = null;
  $("err").textContent = "";
  render();
  if (m === "experiment" && S.q) openQuestion(S.q, 0);
}

let checkTimer = null;
$("input").addEventListener("input", () => {
  clearTimeout(checkTimer);
  if (S.mode !== "experiment") return;
  checkTimer = setTimeout(async () => {
    const text = $("input").value;
    if (!text.trim()) { $("err").textContent = ""; return; }
    try { $("err").textContent = (await api("/api/check", { text })).reason || ""; } catch (e) { /* ignore */ }
  }, 250);
});
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("form").requestSubmit(); }
});
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text || S.busy) return;
  await send(text);
  if (!$("err").textContent) $("input").value = "";
});
$("ee").addEventListener("click", () => run(() => api(S.mode === "demo" ? "/api/demo/ee" : `/api/q/${S.q}/ee`, {})));
$("next").addEventListener("click", nextQuestion);
$("start").addEventListener("click", () => openQuestion(S.q, 1));
$("tab-exp").addEventListener("click", () => switchMode("experiment"));
$("tab-demo").addEventListener("click", () => switchMode("demo"));
$("demo-set").addEventListener("change", (e) => { S.demoSet = e.target.value; renderViews(); });
$("demo-new").addEventListener("click", () => {
  S.demoSet = $("demo-set").value;
  run(() => api("/api/demo/new", { image_set: S.demoSet }));
});
$("show-target").addEventListener("change", (e) => { store("live.showTarget", e.target.checked ? "1" : "0"); render(); });

(async function init() {
  S.meta = await api("/api/meta");
  S.progress = await api("/api/progress");
  $("model").textContent = S.meta.dry_run ? "dry run，不呼叫 API" : `model ${S.meta.model} · r${S.meta.rep}`;
  $("model").classList.toggle("dry", S.meta.dry_run);
  $("demo-path").textContent = S.meta.demo_records;
  $("show-target").checked = load("live.showTarget", "1") === "1";
  buildGrid();
  render();
  const q = load("live.q", null);
  const firstOpen = S.progress.questions.find((p) => p.status === "active") || S.progress.questions.find((p) => p.status === "todo");
  if (q && S.progress.questions.some((p) => p.q === q)) openQuestion(q, 0);
  else if (firstOpen) openQuestion(firstOpen.q, 0);
})();
