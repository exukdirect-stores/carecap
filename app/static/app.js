/* CareCap frontend — a thin renderer over the /api/state + /api/digest responses.
   All logic (missed detection, escalation, refills, digest) is server-side;
   this file only draws and forwards intent. Build 4: captain token auth. */

let S = null; // full state incl. derived
let digest = null; // payload on screen (fresh preview, or an archived record's)
let digestRecord = null; // sent record matching the payload on screen (if any)
let archive = []; // digest summaries from /api/digests
let me = null; // {family_id, family_name, captain}

// The v0 concierge gate from the README: weekly-digest open rate >= 55%.
const V0_OPEN_GATE = 55;
// The demo family's captain token — shown on the sign-in screen on purpose.
const DEMO_TOKEN = "demo-reyes-2026";

function getToken() { return localStorage.getItem("carecap_token") || ""; }
function setToken(t) { t ? localStorage.setItem("carecap_token", t) : localStorage.removeItem("carecap_token"); }

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtMoney = (n) => "$" + Number(n).toFixed(2);
const fmtDate = (iso) =>
  new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
const fmtTime = (iso) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const dayDiff = (iso) =>
  Math.round((new Date(S.now) - new Date(iso.slice(0, 10) + "T00:00:00")) / 86400000);
const memberName = (id) => (S.members.find((m) => m.id === id) || { name: id }).name;
const slotShort = (t) => {
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, body) {
  const opts = { headers: {} };
  const t = getToken();
  let url = path;
  if (t) {
    // The token rides the query string because the preview proxy can drop
    // the Authorization header; the server accepts ?token= either way.
    // The header is kept for direct (non-proxied) access.
    opts.headers["Authorization"] = "Bearer " + t;
    url = path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(t);
  }
  if (body) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  if (r.status === 401) {
    setToken(null);
    location.reload();
    throw new Error("sign in required");
  }
  if (!r.ok) throw new Error((await r.text()) || r.status);
  const j = await r.json();
  if (j && j.derived) S = j; // state responses refresh the cache
  return j;
}

async function refresh() {
  S = await api("/api/state");
  archive = await api("/api/digests");
  renderAll();
}

function renderAll() {
  renderTop();
  renderToday();
  renderTeam();
  renderMoney();
  renderVault();
  renderDigest();
}

/* ------------------------------------------------------- auth (Build 4) */

function renderTop() {
  if (me) {
    $("#family-chip").textContent = `🫂 ${me.family_name} family · captain ${me.captain.split(" ")[0]}`;
    $("#family-chip").classList.remove("hidden");
    $("#sign-out").classList.remove("hidden");
  }
}

function showSignIn(err) {
  $("#app-shell").hidden = true;
  const el = $("#sign-in");
  el.classList.add("active");
  el.innerHTML = `
    <div class="signin-wrap">
      <div class="card signin">
        <h2>The captain's door</h2>
        <p class="sub" style="max-width:440px;margin:0 auto">Siblings read the weekly digest.
        You open this door with your family token — the concierge hands it over on the first call.</p>
        ${err ? `<div class="signin-err">${esc(err)}</div>` : ""}
        <div class="card form"><h3>Sign in</h3>
          <input id="si-token" placeholder="family token" autocomplete="off">
          <button class="btn primary" data-act="do-signin">Sign in</button></div>
        <div class="demo-hint">Demo family (the Reyes): <b>${DEMO_TOKEN}</b> — it's prefilled. Just hit Sign in.</div>
        <div class="or">or start a new family</div>
        <div class="card form col"><h3>New family (concierge onboarding)</h3>
          <input id="nf-name" placeholder="Family name (e.g. Carew)" maxlength="60">
          <input id="nf-captain" placeholder="Captain — your name" maxlength="60">
          <input id="nf-parent" placeholder="Who is the family caring for?" maxlength="60">
          <button class="btn primary" data-act="do-create-family">Create family &amp; get my token</button></div>
      </div>
    </div>`;
  $("#si-token").value = DEMO_TOKEN;
}

function enterApp() {
  $("#sign-in").classList.remove("active");
  $("#sign-in").hidden = true;
  $("#app-shell").hidden = false;
  refresh().catch((err) => toast("Load error: " + err.message));
}

async function boot() {
  $("#sign-out").addEventListener("click", () => {
    setToken(null);
    location.reload();
  });
  if (!getToken()) { showSignIn(); return; }
  try {
    me = await api("/api/families/me");
    enterApp();
  } catch {
    showSignIn("That token wasn't recognized — double-check it, or create a family.");
  }
}

/* ----------------------------------------------------------------- today */

function renderToday() {
  const d = S.derived;
  const now = new Date(S.now);
  const toConfirm = d.today_doses.filter((t) => t.outcome === "pending" || t.outcome === "missed").length;
  const dueLater = d.today_doses.filter((t) => t.outcome === "upcoming").length;

  const bits = [
    d.parent.age != null ? String(d.parent.age) : null,
    d.parent.location || null,
    d.parent.conditions || null,
  ].filter(Boolean);
  let h = `<div>
    <h1>${now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</h1>
    <p class="sub">${esc(d.parent.name)}${bits.length ? " · " + bits.map(esc).join(" · ") : ""}
      ${d.medications.length ? (toConfirm ? `· <b>${toConfirm} dose${toConfirm > 1 ? "s" : ""} to confirm</b>`
        : dueLater ? `· ${dueLater} dose${dueLater > 1 ? "s" : ""} due later today` : "· all doses confirmed ✓") : "· no medications yet"}</p></div>`;

  if (d.alerts.length) {
    h += d.alerts.map((a) => {
      if (a.kind === "dose") {
        const cls = a.level === "escalation" ? "alert-red" : "alert-amber";
        const dates = (a.missed_dates || []).map(fmtDate).join(" · ");
        const dateAttr = a.missed_dates && a.missed_dates[0] ? a.missed_dates[0] : S.now.slice(0, 10);
        return `<div class="alert ${cls}">
          <div><b>${esc(a.message)}</b>${dates ? `<span class="small">missed: ${dates}</span>` : ""}</div>
          <div class="alert-actions">
            <button class="btn small primary" data-act="mark-taken" data-med="${a.med_id}" data-slot="${a.slot}" data-date="${dateAttr}">Mark taken</button>
            <button class="btn small ghost" data-act="mark-skipped" data-med="${a.med_id}" data-slot="${a.slot}" data-date="${dateAttr}">Mark skipped</button>
          </div></div>`;
      }
      const hasTask = d.tasks.some(
        (t) => t.status === "open" && t.title.toLowerCase().startsWith("refill " + a.med.toLowerCase())
      );
      return `<div class="alert alert-blue">
        <div><b>${esc(a.message)}</b><span class="small">the 7-day urgent buffer is closed</span></div>
        <div class="alert-actions">
          ${hasTask ? `<span class="small">refill task already on the team ✓</span>`
            : `<button class="btn small primary" data-act="refill-task" data-med="${esc(a.med)}" data-due="${a.run_out}">Create refill task</button>`}
          <button class="btn small ghost" data-act="refill-med" data-med-id="${a.med_id}" data-name="${esc(a.med)}">Got the new fill — mark refilled ✓</button>
        </div></div>`;
    }).join("");
  }

  // dose board, grouped by medication
  const byMed = {};
  d.today_doses.forEach((t) => {
    (byMed[t.med_id] = byMed[t.med_id] || { meta: t, slots: [] }).slots.push(t);
  });
  h += `<h2 class="h2">Today's doses</h2><div class="dose-grid">`;
  if (!d.today_doses.length) {
    h += `<div class="card center" style="grid-column:1/-1"><h3>No medications yet</h3>
      <p class="sub">First week of onboarding: add ${esc(d.parent.name.split(" ")[0])}'s medications
      and the dose board, alerts, and refill watch all come alive.</p></div>`;
  }
  for (const id in byMed) {
    const g = byMed[id];
    h += `<div class="card"><div class="dose-head"><span><b>${esc(g.meta.med)}</b>
      <span class="small">${esc(g.meta.dose_label)}${g.meta.prn ? " · PRN" : ""}</span></span>
      <button class="btn ghost small" data-act="remove-med" data-med="${g.meta.med_id}"
        data-name="${esc(g.meta.med)}" title="Discontinue (removes its dose history)">✕</button></div>`;
    g.slots.forEach((t) => {
      const today = S.now.slice(0, 10);
      if (t.outcome === "taken")
        h += `<div class="dose-row taken"><span>✓ ${esc(t.slot_label)}</span><span class="small">on time</span></div>`;
      else if (t.outcome === "skipped")
        h += `<div class="dose-row skipped"><span>— ${esc(t.slot_label)} (skipped)</span></div>`;
      else if (t.outcome === "prn")
        h += `<div class="dose-row prn"><span>${esc(t.slot_label)} · as needed</span>
          <span class="row-actions"><button class="btn ghost small" data-act="mark-taken" data-med="${t.med_id}" data-slot="${t.slot}" data-date="${today}">Log dose</button></span></div>`;
      else if (t.outcome === "upcoming")
        h += `<div class="dose-row upcoming"><span>${esc(t.slot_label)}</span><span class="small">upcoming</span></div>`;
      else
        h += `<div class="dose-row due">
          <span>${t.outcome === "missed" ? "⚠ " : ""}${esc(t.slot_label)}${t.outcome === "missed" ? " — not confirmed" : ""}</span>
          <span class="row-actions">
            <button class="btn primary ${t.outcome === "missed" ? "" : "big"}" data-act="mark-taken" data-med="${t.med_id}" data-slot="${t.slot}" data-date="${today}">Take</button>
            <button class="btn ghost" data-act="mark-skipped" data-med="${t.med_id}" data-slot="${t.slot}" data-date="${today}">Skip</button>
          </span></div>`;
    });
    h += `</div>`;
  }
  h += `</div>`;

  // refills at a glance (non-urgent, so the board doesn't double-alert)
  const calm = d.refills.filter((r) => !r.urgent && r.days_left <= 14);
  if (calm.length) {
    h += `<h2 class="h2">Refill watch</h2><div class="card list">` +
      calm.map((r) => `<div class="row"><b>${esc(r.med)}</b><span>${r.days_left} days of supply left</span>
        <span class="small">runs out ${fmtDate(r.run_out)}</span>
        <button class="btn ghost small" data-act="refill-med" data-med-id="${r.med_id}" data-name="${esc(r.med)}">Refilled ✓</button></div>`).join("") + `</div>`;
  }

  // Build 5: the captain adds the next medication here — onboarding continues
  // right on the dose board instead of stopping at an empty page.
  h += `<div class="card med-form"><h3>Add a medication</h3>
    <div class="med-row">
      <input id="med-name" placeholder="Name — e.g. Metformin" maxlength="80">
      <input id="med-dose" placeholder="Dose — e.g. 500 mg · 1 pill" maxlength="80">
    </div>
    <div class="med-row">
      <span class="small">Times</span>
      ${["09:00", "13:00", "18:00", "21:00"].map((t) =>
        `<button type="button" class="chip-toggle" data-act="toggle-slot" data-slot="${t}">${slotShort(t)}</button>`).join("")}
      <input id="med-custom-slot" placeholder="other (HH:MM)" maxlength="5">
    </div>
    <div class="med-row">
      <label class="small"><input type="checkbox" id="med-prn"> PRN — as needed only (no missed-dose alerts, no refill watch)</label>
      <span class="small">supply <input id="med-supply" type="number" min="1" max="365" value="30" class="num"> days</span>
      <button class="btn primary" data-act="add-med">Add to regimen</button>
    </div>
    <input id="med-notes" placeholder="Notes — allergies, take with food, pharmacy, …" maxlength="300">
  </div>`;

  const appts = S.appointments
    .filter((a) => a.when.slice(0, 10) >= S.now.slice(0, 10))
    .sort((x, y) => x.when.localeCompare(y.when))
    .slice(0, 3);
  if (appts.length) {
    h += `<h2 class="h2">Coming up</h2><div class="card list">` +
      appts.map((a) => `<div class="row"><span class="badge teal">${fmtDate(a.when)} · ${a.when.slice(11, 16)}</span><b>${esc(a.title)}</b><span class="small">${esc(a.provider)}</span></div>`).join("") + `</div>`;
  }

  $("#view-today").innerHTML = h;
}

/* ------------------------------------------------------------------ team */

function renderTeam() {
  const d = S.derived;
  let h = `<h2 class="h2">Care team</h2><div class="cards">`;
  for (const m of S.members) {
    const load = d.team_load[m.id] || { open: 0, overdue: 0 };
    h += `<div class="card member"><b>${esc(m.name)}</b>
      <span class="small">${esc(m.role)} · ${esc(m.location)}</span>
      <div class="load"><span class="badge">${load.open} open</span>
      ${load.overdue ? `<span class="badge red">${load.overdue} overdue</span>` : ""}</div></div>`;
  }
  h += `</div><h2 class="h2">Tasks</h2><div class="card list">`;
  const tasks = [...d.tasks].sort((a, b) =>
    a.overdue === b.overdue ? a.due_date.localeCompare(b.due_date) : a.overdue ? -1 : 1
  );
  h += tasks.length
    ? tasks.map((t) => {
        const due = t.status === "done"
          ? `<span class="badge teal">done</span>`
          : t.overdue
            ? `<span class="badge red">overdue · ${fmtDate(t.due_date)}</span>`
            : `<span class="small">due ${fmtDate(t.due_date)}</span>`;
        return `<div class="row task ${t.status === "done" ? "done" : ""}">
          <button class="check" data-act="toggle-task" data-id="${t.id}" title="mark done / reopen">${t.status === "done" ? "✓" : ""}</button>
          <span class="task-title">${esc(t.title)}</span>${due}<span class="small">${esc(memberName(t.assignee))}</span></div>`;
      }).join("")
    : `<div class="row"><span class="small">No tasks yet.</span></div>`;
  h += `</div>
  <div class="card form"><h3>Add a task</h3>
    <input id="task-title" placeholder="e.g. Refill Metformin" maxlength="200">
    <select id="task-assignee">${S.members.filter((m) => m.role !== "parent")
      .map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join("")}</select>
    <input id="task-due" type="date">
    <button class="btn primary" data-act="add-task">Add</button></div>`;
  $("#view-team").innerHTML = h;
  $("#task-due").value = S.now.slice(0, 10);
}

/* ----------------------------------------------------------------- money */

function renderMoney() {
  const d = S.derived;
  const cats = Object.entries(d.mtd).sort((a, b) => b[1] - a[1]);
  const max = cats.length ? cats[0][1] : 1;
  const pend = S.claims.filter((c) => c.status === "pending");

  let h = `<h2 class="h2">Money — this month</h2>
  <div class="money-top">
    <div class="card"><div class="big-num">${fmtMoney(d.mtd_total)}<span class="small">out-of-pocket, month to date</span></div></div>
    <div class="card"><div class="big-num" style="font-size:24px">${fmtMoney(pend.reduce((s, c) => s + c.amount, 0))}<span class="small">${pend.length} claim${pend.length === 1 ? "" : "s"} pending with insurers</span></div></div>
  </div>`;

  h += `<div class="card"><h3>By category</h3>` + (cats.length
    ? cats.map(([c, v]) => `<div class="cat"><span>${esc(c)}</span><div class="bar"><i style="width:${(100 * v / max).toFixed(0)}%"></i></div><b>${fmtMoney(v)}</b></div>`).join("")
    : `<p class="small">Nothing logged this month yet.</p>`) + `</div>`;

  h += `<h2 class="h2">Insurance claims</h2><div class="card list">` +
    S.claims.map((c) => {
      const days = dayDiff(c.submitted);
      const pill = c.status === "approved" ? "ok" : c.status === "denied" ? "bad" : days >= 14 ? "warn" : "";
      return `<div class="row"><b style="width:90px">${fmtMoney(c.amount)}</b><span style="flex:1 1 160px">${esc(c.payer)}</span>
        <span class="small">${esc(c.kind)} · filed ${days}d ago</span>
        <span class="pill ${pill}">${c.status}</span></div>`;
    }).join("") + `</div>`;

  h += `<div class="card form"><h3>Log an expense</h3>
    <input id="exp-amount" type="number" step="0.01" min="0.01" placeholder="0.00" style="flex:0 1 110px">
    <select id="exp-cat" style="flex:0 1 140px">${["Pharmacy", "Transport", "Groceries", "Home care", "Supplies", "Other"].map((c) => `<option>${c}</option>`).join("")}</select>
    <input id="exp-note" placeholder="note">
    <button class="btn primary" data-act="add-expense">Add</button></div>`;
  $("#view-money").innerHTML = h;
}

/* ---------------------------------------------------------------- digest */

function renderDigestPayload(d, rec) {
  const m = d.money;
  let h = `<div class="card digest">
    <div class="digest-head">
      <h2>The ${esc(d.family)} family week</h2>
      <span class="small">${fmtDate(d.week_start)} – ${fmtDate(d.week_end)}</span>
      <div class="row-actions" style="flex-wrap:wrap">
        ${rec
          ? `<span class="badge teal">sent · ${fmtTime(rec.generated_at)}</span>`
          : `<button class="btn primary" data-act="send-digest">Send to family group</button>`}
        <button class="btn ghost" data-act="gen-digest">${rec ? "Back to this week" : "Regenerate"}</button>
      </div>
    </div>
    <p class="headline">${esc(d.headline)}</p>`;

  if (d.alerts.length)
    h += `<h3>Needs attention</h3><ul class="plain">${d.alerts.map((a) => `<li>${esc(a.message)}</li>`).join("")}</ul>`;
  if (d.priorities.length)
    h += `<h3>This week's priorities</h3><ol class="prio">${d.priorities.map((p) => `<li>${esc(p.text)}</li>`).join("")}</ol>`;

  const a = d.adherence;
  h += `<div class="digest-cols">
    <div><h3>Adherence · 7 days</h3>
      <div class="big-num">${a.overall_rate == null ? "—" : a.overall_rate + "%"}</div>
      <table class="mini">${a.by_medication.map((x) =>
        `<tr><td>${esc(x.med)}</td><td>${x.rate == null ? "—" : x.rate + "%"}</td><td class="small">${x.taken}/${x.closed} on time</td></tr>`).join("")}</table></div>
    <div><h3>Money · MTD</h3>
      <div class="big-num">${fmtMoney(m.mtd_total)}</div>
      <ul class="plain small">${Object.entries(m.by_category).map(([c, v]) => `<li>${esc(c)} — ${fmtMoney(v)}</li>`).join("")}</ul>
      <p class="small" style="margin-top:8px">Pending claims: ${m.pending_claims.count} · ${fmtMoney(m.pending_claims.total)} · oldest ${m.pending_claims.oldest_days}d</p></div>
    <div><h3>Appointments · 14 days</h3>
      <ul class="plain small">${d.appointments.map((x) => `<li>${x.label} — ${esc(x.title)} <span class="dim">(${esc(x.provider)})</span></li>`).join("") || "<li>None</li>"}</ul></div>
    <div><h3>Team load</h3>
      <ul class="plain small">${Object.values(d.team_load).map((l) =>
        `<li>${esc(l.name)} — ${l.open} open${l.overdue ? `, <b class="red-text">${l.overdue} overdue</b>` : ""}</li>`).join("")}</ul></div>
  </div></div>`;
  return h;
}

/* Build 3: delivery outbox + the sibling read-moment (the ≥55% v0 gate). */

function renderDeliveryPanel(rec) {
  const members = {};
  S.members.forEach((m) => (members[m.id] = m));
  const sent = rec.sent_to.length;
  const opened = Object.keys(rec.opens).length;
  const rate = sent ? Math.round((100 * opened) / sent) : 0;
  const met = rate >= V0_OPEN_GATE;
  let h = `<div class="card" id="family-inbox">
    <h3>Family inbox <span class="small" style="font-weight:400">· demo outbox — email is simulated, nothing actually sent</span></h3>`;
  rec.sent_to.forEach((id) => {
    const m = members[id] || { name: id, location: "" };
    const del = (rec.deliveries.find((x) => x.member_id === id) || { channel: "email" });
    const at = rec.opens[id];
    h += `<div class="row">
      <b style="flex:1 1 180px">${esc(m.name)} <span class="small" style="font-weight:400">· ${esc(m.location)}</span></b>
      <span class="pill ok">${esc(del.channel)} · ${esc(del.status)}</span>
      ${at
        ? `<span class="badge teal">opened ${fmtTime(at)}</span>`
        : `<button class="btn ghost small" data-act="simulate-open" data-digest="${rec.id}" data-member="${id}">Simulate: ${esc(m.name.split(" ")[0])} opened it</button>`}
    </div>`;
  });
  h += `<div class="gate ${met ? "met" : "unmet"}">Open rate ${opened}/${sent} (${rate}%) — v0 gate ≥${V0_OPEN_GATE}%: ${met ? "met ✓" : "not met yet"}</div></div>`;
  return h;
}

function renderArchive() {
  if (!archive.length) return "";
  let h = `<h2 class="h2">Digest history</h2><div class="card list">` +
    archive.map((r) => `<div class="row">
      <b style="flex:1 1 180px">${fmtDate(r.week_start)} – ${fmtDate(r.week_end)}</b>
      <span class="small">sent ${fmtTime(r.generated_at)}</span>
      <span class="badge ${r.opened === r.sent_to ? "teal" : ""}">${r.opened}/${r.sent_to} opened</span>
      <button class="btn ghost small" data-act="view-digest" data-id="${r.id}">View</button></div>`).join("") +
    `</div>`;
  return h;
}

function renderDigest() {
  const el = $("#view-digest");
  if (digest) {
    let h = renderDigestPayload(digest, digestRecord);
    if (digestRecord) h += renderDeliveryPanel(digestRecord);
    h += renderArchive();
    el.innerHTML = h;
    return;
  }
  el.innerHTML = `<div class="card center">
    <h2>The family week</h2>
    <p class="sub" style="max-width:540px;margin:0 auto 6px">A single, deterministic read of the whole care graph —
    adherence, spend, appointments, team load — plus the rule-based list of what actually matters this week.
    Siblings don't open the app; they read this. The open rate is a v0 gate, so the inbox is real enough to measure it.</p>
    <button class="btn primary big" data-act="gen-digest">Generate family week</button></div>` + renderArchive();
}

/* ----------------------------------------------------------------- vault */

function renderVault() {
  const icons = { legal: "⚖️", insurance: "🛡️", medical: "🩺", notes: "📝" };
  let h = `<h2 class="h2">Document vault</h2><div class="cards">` +
    S.documents.map((doc) => `<div class="card doc">
      <span class="doc-icon">${icons[doc.category] || "📄"}</span>
      <b>${esc(doc.title)}</b>
      <span class="small">${esc(doc.category)} · updated ${fmtDate(doc.updated)}</span>
      <p class="small detail">${esc(doc.detail)}</p></div>`).join("") + `</div>
  <div class="card form"><h3>Add a document</h3>
    <input id="doc-title" placeholder="Title" maxlength="200">
    <select id="doc-cat" style="flex:0 1 130px"><option>legal</option><option>insurance</option><option>medical</option><option>notes</option></select>
    <input id="doc-detail" placeholder="Details / where it lives">
    <button class="btn primary" data-act="add-doc">Add</button></div>`;
  $("#view-vault").innerHTML = h;
}

/* ---------------------------------------------------------------- events */

$("#tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (!b) return;
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + b.dataset.view));
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const act = btn.dataset.act;
  try {
    if (act === "mark-taken" || act === "mark-skipped") {
      await api("/api/doses", {
        med_id: btn.dataset.med,
        date: btn.dataset.date || S.now.slice(0, 10),
        slot: btn.dataset.slot,
        status: act === "mark-taken" ? "taken" : "skipped",
      });
      toast(act === "mark-taken" ? "Dose logged ✓" : "Marked skipped");
    } else if (act === "refill-task") {
      await api("/api/tasks", { title: `Refill ${btn.dataset.med}`, assignee: "patricia", due_date: btn.dataset.due });
      toast("Refill task added to the team");
    } else if (act === "toggle-task") {
      await api(`/api/tasks/${btn.dataset.id}/toggle`);
    } else if (act === "add-task") {
      const title = $("#task-title").value.trim();
      if (!title) return toast("Give the task a title");
      await api("/api/tasks", { title, assignee: $("#task-assignee").value, due_date: $("#task-due").value });
      toast("Task added");
    } else if (act === "add-expense") {
      const amount = parseFloat($("#exp-amount").value);
      if (!(amount > 0)) return toast("Enter an amount");
      await api("/api/expenses", { amount, category: $("#exp-cat").value, note: $("#exp-note").value.trim() });
      toast("Expense logged");
    } else if (act === "gen-digest") {
      digest = await api("/api/digest");
      digestRecord = null;
      renderDigest();
      return; // no state refresh needed
    } else if (act === "send-digest") {
      digestRecord = await api("/api/digests/send");
      digest = digestRecord.payload;
      toast(`Sent to ${digestRecord.sent_to.length} siblings (demo outbox)`);
      await refresh();
      return;
    } else if (act === "simulate-open") {
      digestRecord = await api(`/api/digests/${btn.dataset.digest}/open`, { member_id: btn.dataset.member });
      toast(`${memberName(btn.dataset.member)} opened the digest`);
      await refresh();
      return;
    } else if (act === "view-digest") {
      digestRecord = await api(`/api/digests/${btn.dataset.id}`);
      digest = digestRecord.payload;
      renderDigest();
      return;
    } else if (act === "add-doc") {
      const title = $("#doc-title").value.trim();
      if (!title) return toast("Give the document a title");
      await api("/api/documents", { title, category: $("#doc-cat").value, detail: $("#doc-detail").value.trim() });
      toast("Document added to the vault");
    } else if (act === "toggle-slot") {
      btn.classList.toggle("on");
      return; // selection state only, no API call
    } else if (act === "add-med") {
      const name = $("#med-name").value.trim();
      if (!name) return toast("Give the medication a name");
      const slots = [...document.querySelectorAll(".chip-toggle.on")].map((b) => b.dataset.slot);
      const custom = $("#med-custom-slot").value.trim();
      if (custom) {
        if (!/^\d{1,2}:\d{2}$/.test(custom)) return toast("Custom time must be HH:MM (e.g. 07:30)");
        slots.push(custom.length === 4 ? "0" + custom : custom);
      }
      if (!slots.length) return toast("Pick at least one time chip (or the custom time)");
      await api("/api/medications", {
        name,
        dose_label: $("#med-dose").value.trim(),
        slots,
        prn: $("#med-prn").checked,
        days_supply: parseInt($("#med-supply").value || "30", 10),
        notes: $("#med-notes").value.trim(),
      });
      toast(`${name} added to the regimen — tracking starts today`);
    } else if (act === "remove-med") {
      if (!confirm(`Discontinue ${btn.dataset.name}?\nIts dose history is removed too.`)) return;
      await api(`/api/medications/${btn.dataset.med}/delete`);
      toast(`${btn.dataset.name} discontinued`);
    } else if (act === "refill-med") {
      await api(`/api/medications/${btn.dataset.medId}/refill`, {});
      toast(`${btn.dataset.name} refilled — run-out clock reset to today`);
    }
    await refresh();
  } catch (err) {
    toast("Error: " + err.message);
  }
});

boot();

/* PWA: offline shell. Network-first for the page (always fresh in the
   preview), cache only as a fallback — the SW can never serve stale state. */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  });
}
