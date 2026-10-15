"use strict";

// ── holat ──
let TOKEN = localStorage.getItem("nz_token") || "";
let REPORT = null;            // /api/report keshi
let STOCK = null;             // /api/stock keshi
let salesPer = "today";
let strikeLg = "all";
let qarzMode = "debt";
let stockMode = "low";

const $ = (id) => document.getElementById(id);

// ── format ──
function fmt(n) {
  n = Math.round(n || 0);
  return n.toLocaleString("ru-RU").replace(/,/g, " ").replace(/ /g, " ");
}
function fmtM(n) {
  n = n || 0;
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + " mln";
  if (Math.abs(n) >= 1000) return fmt(n);
  return String(Math.round(n));
}
function pct(n) { return (n == null) ? "—" : (Math.round(n * 10) / 10) + "%"; }
function fmtTime(s) { return s ? s.slice(11, 16) : "—"; }
function fmtDay(s) { return s ? s.slice(8, 10) + "." + s.slice(5, 7) : "—"; }

// ── O'RINDIQ ALMASHUVI belgisi (hamma ro'yxatda bir xil) ──
// Egasi yangi agentlarning ismini yodda tutolmaydi — shuning uchun sana va
// AVVALGI agent ismi bilan ko'rsatiladi ("Farangiz · 🆕 27.07 dan (avval Eliza)").
function seatTag(r) {
  if (!r || !r.seat_changed) return "";
  const since = r.seat_since ? fmtDay(r.seat_since) + " dan" : "yangi";
  const prev = r.seat_prev ? ` · avval ${esc(r.seat_prev)}` : "";
  return `<span class="seat">🆕 ${since}${prev}</span>`;
}

// ── API ──
async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    ...opts,
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN, ...(opts.headers || {}) },
  });
  if (res.status === 401) { showLogin(); throw new Error("auth"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Xatolik");
  return data;
}

function toast(msg, isErr) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (isErr ? " error" : "");
  setTimeout(() => t.classList.add("hidden"), 3200);
}

// ── kirish ──
function showLogin() { $("login-screen").classList.remove("hidden"); $("app").classList.add("hidden"); }
function showApp() { $("login-screen").classList.add("hidden"); $("app").classList.remove("hidden"); }

async function doLogin() {
  const password = $("pin-input").value.trim();
  if (!password) return;
  try {
    const res = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Parol noto'g'ri");
    TOKEN = data.token;
    localStorage.setItem("nz_token", TOKEN);
    $("pin-input").value = "";
    $("login-error").classList.add("hidden");
    showApp();
    init();
  } catch (e) {
    const el = $("login-error"); el.textContent = e.message; el.classList.remove("hidden");
  }
}

// ── yuklash ──
async function loadReport(force) {
  REPORT = await api("/report" + (force ? "" : ""), force ? { } : {});
  renderAll();
}
// ⟳ — endi HAQIQIY yangilash: bot Sales Doctor'dan bugungi ma'lumotni tortadi
// (~5 soniya). Bot vazifani ~15 soniyada oladi, shuning uchun bir necha marta
// qayta so'raymiz va yangi raqam kelishi bilan ekran o'zgaradi.
async function refresh() {
  const btn = $("btn-refresh");
  try {
    btn.textContent = "…";
    btn.classList.add("spin");
    const r = await api("/refresh", { method: "POST" });
    REPORT = r;
    STOCK = null;
    PERIODS = null;                     // ball plan ekrani ham yangilansin
    renderAll();
    if (!$("tab-sklad").classList.contains("hidden")) loadStock();
    if (!$("tab-boshqaruv").classList.contains("hidden")) loadBoshqaruv();

    if (r.quick && r.quick.queued) {
      toast("Yangi ma'lumot olinmoqda...");
      // Bot tortib bo'lgach ekranni o'zi yangilaydi
      [6000, 12000, 20000].forEach(ms => setTimeout(async () => {
        try {
          const fresh = await api("/report");
          if (fresh.updated !== REPORT.updated) { REPORT = fresh; renderAll(); }
        } catch (e) { /* jim */ }
      }, ms));
    } else {
      toast(r.quick ? r.quick.note : "Yangilandi");
    }
  } catch (e) { toast(e.message, true); }
  finally { btn.textContent = "⟳"; btn.classList.remove("spin"); }
}

async function init() {
  try { await loadReport(false); }
  catch (e) { if (e.message !== "auth") toast(e.message, true); }
}

// ── render: hammasi ──
function renderAll() {
  if (!REPORT) return;
  $("weak-warn").classList.toggle("hidden", !REPORT.weak_auth);
  const age = REPORT.age_text ? " · " + REPORT.age_text
            : (REPORT.updated ? " · yangilangan " + REPORT.updated.slice(11, 16) : "");
  $("topbar-date").textContent = REPORT.day_label + age;
  renderBosh();
  renderSavdo();
  renderStrike();
  renderQarz();
}

// ── BOSH ──
function renderBosh() {
  const t = REPORT.totals;
  $("hero-today").textContent = fmtM(t.today) + " so'm";
  const d = REPORT.today_diff_pct;
  const hd = $("hero-diff");
  if (d == null) { hd.textContent = "kecha bilan solishtirish yo'q"; hd.style.color = "rgba(255,255,255,.85)"; }
  else if (d >= 0) { hd.textContent = "▲ " + pct(d) + " (kecha)"; hd.style.color = "#bbf7d0"; }
  else { hd.textContent = "▼ " + pct(Math.abs(d)) + " (kecha)"; hd.style.color = "#fecaca"; }
  $("hero-legs").innerHTML = "Shahar " + fmtM(t.city_today) + "<br>Viloyat " + fmtM(t.region_today);

  const prognoz = REPORT.agents.reduce((a, r) => a + (r.prognoz || 0), 0);
  $("st-month").textContent = fmtM(t.month);
  $("st-prognoz").textContent = fmtM(prognoz);
  $("st-agents").textContent = REPORT.agent_count + (REPORT.observe_count ? " +" + REPORT.observe_count : "");
  $("st-wd").textContent = REPORT.wd_passed + " / " + REPORT.wd_total;

  // signallar
  const sig = REPORT.signals || [];
  $("sig-count").textContent = sig.length;
  $("signals").innerHTML = sig.length ? sig.map((s) =>
    `<div class="sig ${s.level}"><span class="dot"></span><span class="sig-name">${esc(s.name)}</span><span class="sig-text">${esc(s.text)}</span></div>`
  ).join("") : `<div class="empty">Signal yo'q — hammasi joyida ✅</div>`;

  // bugun eng zo'r
  const top = [...REPORT.agents].filter(r => !r.observe).sort((a, b) => b.today_sales - a.today_sales).slice(0, 5);
  $("top-today").innerHTML = top.map((r, i) => rowSales(r, i + 1, "today")).join("") || `<div class="empty">Ma'lumot yo'q</div>`;
  bindRows("top-today");
}

// ── SAVDO ──
function rowSales(r, rank, per) {
  const sales = per === "today" ? r.today_sales : r.month_sales;
  const akb = per === "today" ? r.today_akb : r.month_akb;
  const sub = per === "today"
    ? `${r.today_ball} ball · ${akb} do'kon`
    : `reja ${pct(r.plan_pct)} · ${akb} do'kon`;
  const tag = r.observe ? `<span class="tag">yangi</span>` : "";
  return `<div class="row tap" data-id="${r.sd_id}">
    <div class="row-rank ${rank <= 3 ? "top" : ""}">${rank}</div>
    <div class="row-main"><div class="row-name">${esc(r.name)}${tag}</div>
      <div class="row-sub">${sub}</div>${seatTag(r)}</div>
    <div class="row-right"><div class="row-big">${fmtM(sales)}</div><div class="row-small">${r.league_label}</div></div>
  </div>`;
}
function renderSavdo() {
  const list = [...REPORT.agents].sort((a, b) =>
    (salesPer === "today" ? b.today_sales - a.today_sales : b.month_sales - a.month_sales));
  $("sales-list").innerHTML = list.map((r, i) => rowSales(r, i + 1, salesPer)).join("");
  bindRows("sales-list");
}

// ── STRIKE ──
function strikeColor(p) { return p >= 60 ? "green" : (p >= 45 ? "amber" : "red"); }
function renderStrike() {
  let list = REPORT.agents.filter(r => strikeLg === "all" || r.league === strikeLg);
  list = list.sort((a, b) => a.strike - b.strike);   // eng past tepada
  $("strike-list").innerHTML = list.map((r) => {
    const c = strikeColor(r.strike);
    const tag = r.observe ? `<span class="tag">yangi</span>` : "";
    return `<div class="row srow tap" data-id="${r.sd_id}">
      <div class="srow-top">
        <div class="row-name">${esc(r.name)}${tag} <span class="row-small" style="font-weight:600">${r.league_label}</span></div>
        <div class="srow-pct c-${c}">${pct(r.strike)}</div>
      </div>
      <div class="bar"><div class="bar-fill ${c}" style="width:${Math.min(r.strike, 100)}%"></div></div>
      <div class="srow-meta"><span>kirdi ${r.kirdi} · sotdi ${r.sotdi}</span><span>oy ${fmtM(r.month_sales)} · ${r.month_ball} ball</span></div>
      ${seatTag(r)}
    </div>`;
  }).join("") || `<div class="empty">Ma'lumot yo'q</div>`;
  bindRows("strike-list");
}

// ── QARZ / VAZVRAT ──
function renderQarz() {
  const A = REPORT.agents;
  if (qarzMode === "debt") {
    const list = [...A].sort((a, b) => b.debt - a.debt);
    const total = A.reduce((s, r) => s + r.debt, 0);
    $("qarz-total").innerHTML = `<span>Jami qarz</span><b class="c-red">${fmt(total)} so'm</b>`;
    $("qarz-list").innerHTML = list.map((r) => {
      const c = r.debt_frac > 1 ? "c-red" : (r.debt_frac >= 0.9 ? "c-amber" : "");
      return `<div class="row tap" data-id="${r.sd_id}">
        <div class="row-main"><div class="row-name">${esc(r.name)}</div>
          <div class="row-sub">limit ${fmtM(r.debt_limit)} · ${Math.round(r.debt_frac * 100)}%</div>
          ${seatTag(r)}</div>
        <div class="row-right"><div class="row-big ${c}">${fmt(r.debt)}</div><div class="row-small">${r.league_label}</div></div>
      </div>`;
    }).join("");
  } else {
    const list = [...A].sort((a, b) => b.returns_month - a.returns_month);
    const total = A.reduce((s, r) => s + r.returns_month, 0);
    $("qarz-total").innerHTML = `<span>Oylik vazvrat</span><b class="c-amber">${fmt(total)} so'm</b>`;
    $("qarz-list").innerHTML = list.map((r) =>
      `<div class="row tap" data-id="${r.sd_id}">
        <div class="row-main"><div class="row-name">${esc(r.name)}</div>
          <div class="row-sub">to'liq ${fmtM(r.returns_full)} · qisman ${fmtM(r.returns_partial)}</div>
          ${seatTag(r)}</div>
        <div class="row-right"><div class="row-big">${fmt(r.returns_month)}</div><div class="row-small">${pct(r.returns_pct)} savdodan</div></div>
      </div>`).join("");
  }
  bindRows("qarz-list");
}

// ── SKLAD ──
async function loadStock() {
  try {
    if (!STOCK) STOCK = await api("/stock");
    renderStock();
  } catch (e) { toast(e.message, true); }
}
function stockDaysColor(d) { return d == null ? "" : (d < 2 ? "c-red" : (d <= 5 ? "c-amber" : "c-green")); }
function renderStock() {
  if (!STOCK) return;
  $("stock-meta").innerHTML = `<span>Jami <b>${STOCK.count}</b> mahsulot · kritik <b class="c-red">${STOCK.critical}</b></span><span>${STOCK.updated.slice(0, 10)}</span>`;
  const items = stockMode === "low" ? STOCK.low : STOCK.full;
  if (!items.length) { $("stock-list").innerHTML = `<div class="empty">Ro'yxat bo'sh</div>`; return; }
  $("stock-list").innerHTML = items.map((it) => {
    const c = stockDaysColor(it.days);
    const days = it.days == null ? "∞" : (it.days + " kun");
    return `<div class="row">
      <div class="row-main"><div class="row-name" style="font-size:14.5px">${esc(it.name)}</div><div class="row-sub">${esc(it.cat)}</div></div>
      <div class="row-right"><div class="row-big">${fmt(it.stock)}</div><div class="row-small ${c}">${days}</div></div>
    </div>`;
  }).join("");
}

// ── BOSHQARUV: ulanish + yangilash ──
let CONN = null;
let bqMode = "ulanish";

async function loadConn() {
  try {
    CONN = await api("/connections");
    renderConn();
  } catch (e) { toast(e.message, true); }
}

function renderConn() {
  if (!CONN) return;

  // Kutilayotgan so'rovlar
  const pb = $("pending-box");
  if (CONN.pending.length) {
    pb.innerHTML = `<div class="section-head"><span>⏳ Ulanish so'rovlari</span>
      <span class="pill">${CONN.pending.length}</span></div>` +
      CONN.pending.map(p => `<div class="pend">
        <div class="pend-top">${esc(p.name)} <span class="row-small">${esc(p.code)}</span></div>
        <div class="pend-sub">${esc(p.who)} · ${fmtDay(p.requested_at)} ${fmtTime(p.requested_at)}</div>
        <div class="pend-acts">
          <button class="act-btn ok" data-appr="${esc(p.code)}" data-chat="${p.chat_id}">✅ Tasdiqlash</button>
          <button class="act-btn danger" data-rej="${esc(p.code)}" data-chat="${p.chat_id}">❌ Rad etish</button>
        </div></div>`).join("");
  } else pb.innerHTML = "";

  $("conn-on").textContent = CONN.connected;
  $("conn-off").textContent = CONN.not_connected;
  $("conn-total").textContent = `jami ${CONN.total}`;

  $("conn-list").innerHTML = CONN.rows.map(r => {
    const sup = r.role === "supervisor";
    const tag = sup ? `<span class="tag">super</span>` : (r.observe ? `<span class="tag">yangi</span>` : "");
    const act = r.connected
      ? `<button class="act-btn danger" data-unb="${esc(r.code)}" data-nm="${esc(r.name)}">Uzish</button>`
      : `<span class="row-small">kod: ${esc(r.code)}</span>`;
    return `<div class="row conn">
      <span class="dot-st ${r.connected ? "on" : "off"}"></span>
      <div class="row-main">
        <div class="row-name">${esc(r.name)}${tag}</div>
        <div class="row-sub">${esc(r.league_label)}${r.area ? " · " + esc(r.area) : ""}${
          r.connected ? " · ulangan " + fmtDay(r.bound_at) : ""}</div>
        ${seatTag(r)}
      </div>
      <div class="row-right">${act}</div>
    </div>`;
  }).join("") || `<div class="empty">Ro'yxat bo'sh</div>`;

  // Sync holati
  const s = CONN.sync;
  $("sync-status").innerHTML = s
    ? `Oxirgi yangilash: <b>${fmtDay(s.at)} ${fmtTime(s.at)}</b><br>
       Turi: ${esc(s.type || "—")} · Natija: ${s.status === "ok" ? "✅ ok" : "❌ " + esc(s.status)}
       ${s.note ? "<br><span class='row-small'>" + esc(s.note) + "</span>" : ""}
       ${CONN.queued ? "<br>⏳ Navbatda: " + CONN.queued + " ta vazifa" : ""}`
    : "Ma'lumot yo'q";

  const bl = $("sync-blackout");
  if (CONN.blackout) { bl.textContent = "⏳ " + CONN.blackout; bl.classList.remove("hidden"); }
  else bl.classList.add("hidden");

  $("jobs-list").innerHTML = CONN.jobs.map(j => `<div class="row">
      <div class="row-main"><div class="row-name" style="font-size:14px">${esc(j.label)}</div>
        <div class="row-sub">${fmtDay(j.created_at)} ${fmtTime(j.created_at)}${
          j.result ? " · " + esc(String(j.result).slice(0, 40)) : ""}</div></div>
      <div class="row-right"><span class="jst ${j.status}">${j.status}</span></div>
    </div>`).join("") || `<div class="empty">Hali vazifa yo'q</div>`;

  bindConnActions();
}

function bindConnActions() {
  document.querySelectorAll("[data-appr]").forEach(b => b.addEventListener("click", async () => {
    await connAction("/bind/approve", { code: b.dataset.appr, chat_id: +b.dataset.chat }, "Tasdiqlandi");
  }));
  document.querySelectorAll("[data-rej]").forEach(b => b.addEventListener("click", async () => {
    await connAction("/bind/reject", { code: b.dataset.rej, chat_id: +b.dataset.chat }, "Rad etildi");
  }));
  document.querySelectorAll("[data-unb]").forEach(b => b.addEventListener("click", () => {
    askConfirm(b.dataset.unb, b.dataset.nm);
  }));
}

// Natijani bir necha marta tekshiradi (bot 15 sekundda bir marta oladi)
function refreshSoon() { [3000, 9000, 18000, 30000].forEach(ms => setTimeout(loadConn, ms)); }

function lockBtns(on) {
  document.querySelectorAll("#tab-boshqaruv .act-btn, #btn-sync-fast, #btn-sync-full")
    .forEach(b => { b.disabled = on; b.style.opacity = on ? ".5" : ""; });
}

async function connAction(path, body, okMsg) {
  lockBtns(true);
  try {
    const r = await api(path, { method: "POST", body: JSON.stringify(body) });
    toast(r.ok ? okMsg + " — bot bajaradi (~15 sekund)" : r.note);
    refreshSoon();
  } catch (e) { toast(e.message, true); }
  finally { setTimeout(() => lockBtns(false), 3000); }
}

// Uzish tasdig'i (ism yozib)
let unbTarget = null;
function askConfirm(code, name) {
  unbTarget = { code, name };
  $("confirm-text").innerHTML = `<b>${esc(name)}</b> botdan uziladi va hisobot olmaydi.<br>
    Tasdiqlash uchun ismini yozing: <b>${esc(name)}</b>`;
  $("confirm-input").value = "";
  $("confirm-error").classList.add("hidden");
  $("confirm").classList.remove("hidden");
}
async function doUnbind() {
  if (!unbTarget) return;
  try {
    const r = await api("/bind/disconnect", {
      method: "POST",
      body: JSON.stringify({ code: unbTarget.code, confirm_name: $("confirm-input").value }),
    });
    $("confirm").classList.add("hidden");
    toast(r.ok ? "Uzildi — bot bajaradi (~15 sekund)" : r.note);
    refreshSoon();
  } catch (e) {
    const el = $("confirm-error"); el.textContent = e.message; el.classList.remove("hidden");
  }
}

async function doSync(mode) {
  lockBtns(true);
  try {
    const r = await api("/sync", { method: "POST", body: JSON.stringify({ mode }) });
    toast(r.ok ? (r.blackout ? "Navbatga qo'yildi. " + r.blackout : "Yangilash boshlandi — bot bajaradi")
               : r.note);
    refreshSoon();
  } catch (e) { toast(e.message, true); }
  finally { setTimeout(() => lockBtns(false), 3000); }
}

// ── BALL PLAN: «oy varaqasi» ──
let PERIODS = null;      // /api/periods
let SHEET = null;        // ochilgan varaqa
let bpYm = null;         // ochilgan oy kaliti

// Har safar SERVERDAN o'qiydi (keshlanmaydi). Sabab: bitta varaqani kompyuter va
// telefondan ochish mumkin — keshlansa telefon eski raqamlarni ko'rsatib, saqlaganda
// kompyuterdagi ishni bosib ketardi (2026-07-31 da shu chalkashlik bo'ldi).
async function loadPeriods() {
  try {
    PERIODS = await api("/periods");
    if (!bpYm) bpYm = PERIODS.default_ym;
    await loadSheet(bpYm);
  } catch (e) { toast(e.message, true); }
}

function loadBoshqaruv() {
  loadConn();
  if (bqMode === "ballplan") loadPeriods();
}

async function loadSheet(ym) {
  SHEET = await api("/period/" + ym);
  bpYm = ym;
  renderSheet();
}

function monthOptions() {
  // Mavjud varaqalar + keyingi oy (hali ochilmagan bo'lsa)
  const seen = new Set(PERIODS.sheets.map(s => s.period_ym));
  const opts = PERIODS.sheets.map(s => ({ ym: s.period_ym, label: s.label }));
  [PERIODS.next_period, PERIODS.today_period].forEach(ym => {
    if (!seen.has(ym)) { opts.unshift({ ym, label: ymLabel(ym) }); seen.add(ym); }
  });
  return opts.sort((a, b) => b.ym.localeCompare(a.ym));
}
const UZ_MONTHS = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
                   "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];
function ymLabel(ym) { return UZ_MONTHS[+ym.slice(5, 7)] + " " + ym.slice(0, 4); }

function renderSheet() {
  if (!SHEET) return;
  const frozen = !SHEET.editable;
  const busy = SHEET.pending;                 // bot hali bajarmagan vazifa bor

  $("bp-month").textContent = SHEET.label;
  $("bp-status").innerHTML = busy
    ? `<span class="st-busy">⏳ ${busy === "period_publish" ? "E'lon qilinmoqda" : "Namuna yuborilmoqda"} — bot bajarmoqda…</span>`
    : (frozen
      ? `<span class="st-frozen">🔒 E'lon qilingan${SHEET.checksum ? " · muhr " + esc(SHEET.checksum) : ""}</span>`
      : `<span class="st-draft">✏️ Qoralama — agentlar ko'rmaydi</span>`);
  $("bp-head").className = "period-head " + (busy ? "busy" : (frozen ? "frozen" : "draft"));
  if (busy) setTimeout(() => loadSheet(bpYm).catch(() => {}), 5000);   // o'zi yangilanadi

  // Oy tanlash
  const sel = $("bp-select");
  sel.innerHTML = monthOptions().map(o =>
    `<option value="${o.ym}" ${o.ym === bpYm ? "selected" : ""}>${esc(o.label)}</option>`).join("");

  const act = PERIODS.active;
  $("bp-note").innerHTML = frozen
    ? `Bu varaqa <b>muzlagan</b>. ${SHEET.starts.slice(8, 10)}.${SHEET.starts.slice(5, 7)} dan
       kuchda. O'zgartirish uchun keyingi oy varaqasini oching.`
    : `Yozgan raqamlaringizni <b>agentlar hali ko'rmaydi</b>. E'lon qilsangiz —
       <b>${SHEET.starts.slice(8, 10)}.${SHEET.starts.slice(5, 7)}.${SHEET.starts.slice(0, 4)}</b>
       dan kuchga kiradi.<br>Hozir amalda: <b>${act ? esc(act.label) : "YAML (boshlang'ich)"}</b>.`;

  $("bp-prizes").checked = SHEET.prizes_enabled;
  $("bp-prizes").disabled = frozen;
  $("bp-growth").checked = SHEET.growth_enabled;
  $("bp-growth").disabled = frozen;
  $("bp-changed").textContent = SHEET.changed_count ? SHEET.changed_count + " o'zgardi" : "o'zgarish yo'q";

  const obs = SHEET.rows.filter(r => r.observe);
  $("bp-list").innerHTML = SHEET.rows.map(r => {
    const nw = r.is_new ? `<span class="tag new">ro'yxatga qo'shildi</span>` : "";
    const diff = r.changed
      ? `<span class="bp-was">${r.was} →</span>` : "";
    // XUDUD har doim ko'rinadi — yangi agentni ismidan emas, xududidan taniydi
    const where = `${r.league_label}${r.area ? " · " + esc(r.area) : ""}`;
    // KUZATUVdagi agentga qo'yilgan plan uning kartasida KO'RINMAYDI — ochiq aytamiz
    const obsLine = r.observe
      ? `<div class="row-sub c-amber">👁 Kuzatuvda${r.observe_until ? " " + fmtDay(r.observe_until) + " gacha" : ""} — plan kartada ko'rinmaydi</div>`
      : "";
    return `<div class="row bp-row ${r.changed ? "changed" : ""} ${r.observe ? "obs" : ""}">
      <div class="row-main">
        <div class="row-name">${esc(r.name)}${nw}</div>
        <div class="row-sub">${where}</div>
        ${seatTag(r)}
        ${obsLine}
      </div>
      <div class="bp-edit">
        ${diff}
        <input class="bp-inp" type="number" inputmode="numeric" min="0" max="500"
               data-sd="${esc(r.sd_id)}" value="${r.ball_plan}" ${frozen ? "disabled" : ""}>
        <span class="bp-unit">ball</span>
      </div>
    </div>`;
  }).join("") || `<div class="empty">Agent yo'q</div>`;

  let extra = "";
  if (obs.length) {
    extra += `<div class="explain amber">👁 <b>${obs.length} ta agent kuzatuv rejimida</b>
      (${obs.map(r => esc(r.name) + (r.area ? " — " + esc(r.area) : "")).join(", ")}).
      Ularga plan yozsangiz saqlanadi, lekin <b>kuzatuv tugagunicha kartasida
      ko'rinmaydi</b> — yangi agent shoshilmasin degan qoida.</div>`;
  }
  if (SHEET.gone.length) {
    extra += `<div class="explain">ℹ️ Oldingi varaqada bor edi, hozir faol emas:
      ${SHEET.gone.map(g => esc(g.sd_id)).join(", ")}</div>`;
  }
  $("bp-gone").innerHTML = extra;

  $("bp-actions").classList.toggle("hidden", frozen);

  // ✏️ TUZATISH — e'lon qilingan varaqani oy TUGAMAGUNCHA to'g'rilash mumkin.
  // Oy tugagach muzlaydi: o'sha oy bonusi shu raqamlar bilan hisoblangan.
  $("bp-fix").classList.toggle("hidden", !(frozen && SHEET.can_fix && !busy));
  if (frozen && SHEET.can_fix) {
    $("bp-fix-hint").innerHTML = SHEET.is_future
      ? `Bu oy hali boshlanmagan — tuzatsangiz hech kim sezmaydi.`
      : `Bu oy hali davom etyapti — tuzatsangiz bo'ladi. Tuzatgach
         <b>qayta E'LON QILISH</b>ni unutmang, aks holda reja amal qilmaydi.`;
  }
  if (frozen && !SHEET.can_fix) {
    $("bp-note").innerHTML = `🔒 Bu oy <b>tugagan</b> — varaqa muzlagan, o'zgartirib
      bo'lmaydi. O'sha oy bonusi shu raqamlar bilan hisoblangan.`;
  }

  // Tuzatish tarixi (qaysi nusxa qachon almashtirilgan)
  const h = SHEET.history || [];
  $("bp-hist").innerHTML = h.length
    ? `<div class="explain">📜 <b>Tuzatishlar tarixi</b><br>` + h.map(v =>
        `${v.version}-nusxa · e'lon ${fmtDay(v.published_at)} ${fmtTime(v.published_at)}
         · almashtirildi ${fmtDay(v.replaced_at)} ${fmtTime(v.replaced_at)}
         · muhr ${esc(v.checksum || "—")}`).join("<br>") + `</div>`
    : "";

  bpLock(!!busy);            // bot bajarayotganda takror bosib bo'lmaydi

  $("bp-list").querySelectorAll(".bp-inp").forEach(i =>
    i.addEventListener("input", () => i.closest(".bp-row").classList.add("changed")));
}

function collectPlans() {
  const out = {};
  $("bp-list").querySelectorAll(".bp-inp").forEach(i => {
    out[i.dataset.sd] = Math.max(0, Math.min(500, parseInt(i.value || "0", 10) || 0));
  });
  return out;
}

function bpLock(on) {
  ["bp-save", "bp-preview", "bp-publish", "bp-reopen"].forEach(id => {
    const b = $(id); if (b) { b.disabled = on; b.style.opacity = on ? ".5" : ""; }
  });
}

async function bpSave(quiet) {
  bpLock(true);
  try {
    await api("/period/" + bpYm + "/save", {
      method: "POST",
      body: JSON.stringify({ plans: collectPlans(),
                             prizes_enabled: $("bp-prizes").checked,
                             growth_enabled: $("bp-growth").checked }),
    });
    PERIODS = null;
    await loadPeriods();
    if (!quiet) toast("Saqlandi — agentlar hali ko'rmaydi");
    return true;
  } catch (e) { toast(e.message, true); return false; }
  finally { bpLock(false); }
}

async function bpPreview() {
  if (!(await bpSave(true))) return;
  bpLock(true);
  try {
    const r = await api("/period/" + bpYm + "/preview", { method: "POST" });
    toast(r.ok ? "Namuna Telegramga yuborilmoqda (~15 sekund)" : r.note);
  } catch (e) { toast(e.message, true); }
  finally { setTimeout(() => bpLock(false), 3000); }
}

function bpAskPublish() {
  const m = SHEET.label.split(" ")[0];
  const isFix = (SHEET.version || 1) > 1;
  $("pub-text").innerHTML = (isFix
    ? `<b>${esc(SHEET.label)}</b> varaqasi <b>${SHEET.version}-nusxa</b> bo'lib qayta
       e'lon qilinadi. Agentlar avvalgi raqamlarni ko'rgan edi — yangisi darrov
       o'rnini oladi.<br>`
    : `<b>${esc(SHEET.label)}</b> varaqasi e'lon qilinadi.<br>`) + `
    ${SHEET.changed_count} ta agentda ball plani o'zgaradi.
    ${SHEET.prizes_enabled ? "" : "<br>🚫 <b>Podium sovrini o'chiriladi.</b>"}
    ${SHEET.growth_enabled ? "" : "<br>🚫 <b>O'sish sovrini (700 ming) o'chiriladi.</b>"}
    <br><br>Tasdiqlash uchun oy nomini yozing: <b>${esc(m)}</b>`;
  $("pub-input").value = "";
  $("pub-error").classList.add("hidden");
  $("pubconfirm").classList.remove("hidden");
}

async function bpDoPublish() {
  try {
    if (!(await bpSave(true))) return;
    const r = await api("/period/" + bpYm + "/publish", {
      method: "POST",
      body: JSON.stringify({ confirm_month: $("pub-input").value }),
    });
    $("pubconfirm").classList.add("hidden");
    toast(r.ok ? "E'lon qilindi — bot tasdiqlaydi (~15 sekund)" : r.note);
    setTimeout(async () => { PERIODS = null; await loadPeriods(); }, 4000);
  } catch (e) {
    const el = $("pub-error"); el.textContent = e.message; el.classList.remove("hidden");
  }
}

async function bpReopen() {
  if (!confirm(`${SHEET.label} varaqasini tuzatishga ochamizmi?\n\n` +
               `Tuzatib bo'lgach QAYTA E'LON QILISH shart — aks holda bu oy uchun ` +
               `reja amal qilmaydi.`)) return;
  bpLock(true);
  try {
    const r = await api("/period/" + bpYm + "/reopen", { method: "POST" });
    toast(r.note);
    PERIODS = null;
    await loadPeriods();
  } catch (e) { toast(e.message, true); }
  finally { bpLock(false); }
}

// ── AGENT DRILL ──
async function openDrill(sd_id) {
  $("drill").classList.remove("hidden");
  $("drill-body").innerHTML = `<div class="empty">Yuklanmoqda...</div>`;
  try {
    const d = await api("/agent/" + sd_id);
    $("drill-body").innerHTML = drillHTML(d);
  } catch (e) { $("drill-body").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
function closeDrill() { $("drill").classList.add("hidden"); }

function kv(k, v, cls) { return `<div class="kv"><span class="k">${k}</span><span class="v ${cls || ""}">${v}</span></div>`; }
function drillHTML(d) {
  const r = d.row || {}, ball = d.ball || {}, plan = d.plan || {}, toy = d.toy || {};
  const sc = plan.status_scheme === "ok" ? "ok" : "warn";
  let shops = "";
  if (d.debts && d.debts.length) {
    shops = `<div class="dcard"><h4>💳 Qarzli do'konlar (${d.debts.length})</h4>` +
      d.debts.slice(0, 30).map(s => `<div class="shop-line"><span class="s-name">${esc(s.shop)}${s.age != null ? " · " + s.age + " kun" : ""}</span><span class="s-val c-red">${fmt(s.debt)}</span></div>`).join("") +
      `</div>`;
  }
  let rets = "";
  const rf = d.returns_full || [], rp = d.returns_partial || [];
  if (rf.length || rp.length || d.returns_month) {
    rets = `<div class="dcard"><h4>↩️ Vazvrat · oy jami ${fmt(d.returns_month)}</h4>` +
      (rf.length ? `<div class="row-sub" style="margin:2px 0 6px">To'liq (${d.returns_date}):</div>` + rf.map(s => `<div class="shop-line"><span class="s-name">${esc(s.shop)}</span><span class="s-val c-red">${fmt(s.sum)}</span></div>`).join("") : "") +
      (rp.length ? `<div class="row-sub" style="margin:8px 0 6px">Qisman (${d.returns_date}):</div>` + rp.map(s => `<div class="shop-line"><span class="s-name">${esc(s.shop)}</span><span class="s-val c-amber">${fmt(s.sum)}</span></div>`).join("") : "") +
      (!rf.length && !rp.length ? `<div class="row-sub">Kecha vazvrat bo'lmadi.</div>` : "") +
      `</div>`;
  }
  return `
    <div class="drill-title">${esc(r.name || ball.name || "")}${r.observe ? ' <span class="tag">yangi</span>' : ""}</div>
    <div class="drill-sub">${r.league_label || ""} · ${esc(r.code || "")}</div>

    <div class="dcard"><h4>📊 Savdo reja</h4>
      ${kv("Bajarildi", pct(plan.plan_pct), plan.plan_pct >= 100 ? "c-green" : (plan.plan_pct >= 80 ? "c-amber" : "c-red"))}
      ${kv("Oylik savdo", fmt(plan.sales_done) + " so'm")}
      ${kv("Reja", fmt(plan.sales_plan) + " so'm")}
      ${kv("Prognoz", fmt(Math.round(plan.prognoz)) + " so'm · " + pct(plan.prognoz_pct))}
      ${kv("Kuniga kerak", fmt(Math.round(plan.daily_required)) + " so'm")}
      ${kv("Bugun", fmt(plan.today_sales) + " so'm")}
      <div class="status-box ${sc}" style="margin-top:10px">${esc(plan.status_text || "")}</div>
    </div>

    <div class="dcard"><h4>🎯 Ball · Strike</h4>
      ${kv("Oylik ball", (ball.month_ball ?? "—") + " / " + (ball.ball_plan ?? "—") + " reja")}
      ${kv("Bugungi ball", ball.ball_today ?? "—")}
      ${kv("Strike rate", pct(r.strike), "c-" + strikeColor(r.strike || 0))}
      ${kv("Kirdi / Sotdi", (r.kirdi ?? 0) + " / " + (r.sotdi ?? 0))}
      ${kv("Prognoz ball", Math.round(ball.prognoz_ball ?? 0))}
      ${r.today_akb != null ? kv("Bugun do'kon (AKB)", r.today_akb) : ""}
    </div>

    <div class="dcard"><h4>🎁 Happy Toy</h4>
      ${kv("Hozirgi bloklar", (Math.round((toy.blocks || 0) * 10) / 10))}
      ${toy.next_blocks ? kv("Keyingi daraja", toy.next_blocks + " blok → " + fmt(toy.next_bonus) + " so'm") : kv("Daraja", "eng yuqori bosqichda ✅", "c-green")}
      ${toy.to_next ? kv("Yetishga", (Math.round(toy.to_next * 10) / 10) + " blok · kuniga " + (Math.round((toy.per_day_needed || 0) * 10) / 10)) : ""}
    </div>

    <div class="dcard"><h4>💳 Qarz</h4>
      ${kv("Jami qarz", fmt(d.debt_total) + " so'm", d.debt_total > d.debt_limit ? "c-red" : "")}
      ${kv("Limit", fmt(d.debt_limit) + " so'm")}
    </div>
    ${shops}
    ${rets}
  `;
}

// ── qatorlarga bosish ──
function bindRows(containerId) {
  $(containerId).querySelectorAll(".row.tap").forEach((el) => {
    el.addEventListener("click", () => openDrill(el.dataset.id));
  });
}

// ── tab almashtirish ──
function switchTab(name) {
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  ["bosh", "savdo", "strike", "qarz", "sklad", "boshqaruv"].forEach(t =>
    $("tab-" + t).classList.toggle("hidden", t !== name));
  if (name === "sklad") loadStock();
  if (name === "boshqaruv") loadBoshqaruv();
  window.scrollTo(0, 0);
}

function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// ── ulash ──
function wire() {
  $("pin-btn").addEventListener("click", doLogin);
  $("pin-input").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });

  // 👁 Parolni ko'rsatish / berkitish
  const eye = $("pin-eye");
  if (eye) eye.addEventListener("click", () => {
    const inp = $("pin-input");
    const show = inp.type === "password";
    inp.type = show ? "text" : "password";
    eye.textContent = show ? "🙈" : "👁";
    eye.classList.toggle("on", show);
    inp.focus();
  });
  $("btn-refresh").addEventListener("click", refresh);
  $("drill-close").addEventListener("click", closeDrill);
  $("drill").addEventListener("click", (e) => { if (e.target.id === "drill") closeDrill(); });

  document.querySelectorAll(".nav-btn").forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));

  // chip guruhlari
  chipGroup("tab-savdo", "per", (v) => { salesPer = v; renderSavdo(); });
  chipGroup("tab-strike", "lg", (v) => { strikeLg = v; renderStrike(); });
  chipGroup("tab-qarz", "qv", (v) => { qarzMode = v; renderQarz(); });
  chipGroup("tab-sklad", "sk", (v) => { stockMode = v; renderStock(); });
  chipGroup("tab-boshqaruv", "bq", (v) => {
    bqMode = v;
    $("bq-ulanish").classList.toggle("hidden", v !== "ulanish");
    $("bq-yangilash").classList.toggle("hidden", v !== "yangilash");
    $("bq-ballplan").classList.toggle("hidden", v !== "ballplan");
    if (v === "ballplan") loadPeriods();
  });

  // Boshqaruv tugmalari
  $("btn-sync-fast").addEventListener("click", () => doSync("fast"));
  $("btn-sync-full").addEventListener("click", () => doSync("full"));

  // Ball plan («oy varaqasi»)
  $("bp-select").addEventListener("change", (e) => {
    loadSheet(e.target.value).catch(err => toast(err.message, true));
  });
  $("bp-save").addEventListener("click", () => bpSave(false));
  $("bp-preview").addEventListener("click", bpPreview);
  $("bp-publish").addEventListener("click", bpAskPublish);
  $("bp-reopen").addEventListener("click", bpReopen);
  $("pub-ok").addEventListener("click", bpDoPublish);
  $("pub-cancel").addEventListener("click", () => $("pubconfirm").classList.add("hidden"));
  $("pubconfirm").addEventListener("click", (e) => {
    if (e.target.id === "pubconfirm") $("pubconfirm").classList.add("hidden");
  });
  $("confirm-ok").addEventListener("click", doUnbind);
  $("confirm-cancel").addEventListener("click", () => $("confirm").classList.add("hidden"));
  $("confirm").addEventListener("click", (e) => {
    if (e.target.id === "confirm") $("confirm").classList.add("hidden");
  });
}
function chipGroup(tabId, attr, cb) {
  $(tabId).querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => {
    $(tabId).querySelectorAll(".chip").forEach(x => x.classList.remove("active"));
    c.classList.add("active");
    cb(c.dataset[attr]);
  }));
}

// ── start ──
wire();
if (TOKEN) { showApp(); init(); } else { showLogin(); }
