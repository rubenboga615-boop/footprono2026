// Console FootProba : tableau de bord, actions, suivi, fichiers, exploitation.
// Le catalogue des actions vient du serveur : une action ajoutée côté serveur apparaît
// ici sans modifier ce fichier. Aucune donnée n'est insérée en HTML brut (textContent).
"use strict";

const API = "/api/v1";
const CONSOLE = "/admin/console";
const TOKEN_KEY = "fp_admin_token";
const POLL_MS = 1500;
const FAMILY_ICON = { Données: "i-db", Moteur: "i-chip", Application: "i-phone", Comptes: "i-user", Diagnostic: "i-pulse" };
const PAGES = [
  { id: "dashboard", hash: "#/", title: "Tableau de bord", icon: "i-home" },
  { id: "actions", hash: "#/actions", title: "Actions", icon: "i-bolt" },
  { id: "journal", hash: "#/journal", title: "Journal", icon: "i-list" },
  { id: "fichiers", hash: "#/fichiers", title: "Fichiers", icon: "i-file" },
  { id: "codes", hash: "#/codes", title: "Codes du jour", icon: "i-ticket" },
  { id: "comptes", hash: "#/comptes", title: "Comptes", icon: "i-user" },
  { id: "paiements", hash: "#/paiements", title: "Paiements", icon: "i-card" },
  { id: "versions", hash: "#/versions", title: "Versions de l'app", icon: "i-phone" },
  { id: "securite", hash: "#/securite", title: "Sécurité", icon: "i-shield" },
];

let token = readToken();
let me = null;
let catalog = null;
let lastDashboard = null;
let timer = null;
let prefill = null; // { action, params } pour « Relancer »

// --- Outils -------------------------------------------------------------------

function readToken() {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function writeToken(value) {
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* stockage indisponible : la session dure le temps de la page */ }
}

class ApiError extends Error {
  constructor(message, status, code) { super(message); this.status = status; this.code = code; }
}

async function api(method, path, body, extra) {
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  let payload;
  if (body instanceof Blob) { payload = body; headers["Content-Type"] = "application/octet-stream"; }
  else if (body !== undefined) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const response = await fetch(API + path, { method, headers, body: payload, ...(extra || {}) });
  let data = null;
  try { data = await response.json(); } catch { /* réponse vide */ }
  if (response.status === 401 && path !== "/auth/console-login") { logout(); throw new ApiError("Session expirée : reconnecte-toi.", 401); }
  if (!response.ok) {
    const error = data && data.error ? data.error : {};
    throw new ApiError(error.message || `Erreur ${response.status}`, response.status, error.code);
  }
  return data;
}

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    // Par le CSSOM : la politique de contenu bloque les attributs « style ».
    else if (key === "style") el.style.cssText = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}
const SVG = "http://www.w3.org/2000/svg";
function icon(name) {
  const svg = document.createElementNS(SVG, "svg");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", "#" + name);
  svg.append(use);
  return svg;
}
function svgEl(tag, attrs, ...children) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  for (const c of children) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}
function pill(text, kind, dot) { return h("span", { class: "pill " + (kind || "") }, dot ? h("i") : null, text); }

const fmtDateTime = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
const fmtTime = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
const fmtNumber = new Intl.NumberFormat("fr-FR");
function number(n) { return fmtNumber.format(n); }
function when(value) {
  if (!value) return "—";
  const d = new Date(value);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  if (d.toDateString() === today.toDateString()) return "aujourd'hui " + fmtTime.format(d);
  if (d.toDateString() === yesterday.toDateString()) return "hier " + fmtTime.format(d);
  return fmtDateTime.format(d);
}
function duration(seconds) {
  if (seconds === null || seconds === undefined) return "";
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return seconds + " s";
  if (seconds < 3600) return Math.round(seconds / 60) + " min";
  return Math.floor(seconds / 3600) + " h " + String(Math.round((seconds % 3600) / 60)).padStart(2, "0");
}
function between(start, end) {
  if (!start) return "";
  return duration(((end ? new Date(end) : new Date()) - new Date(start)) / 1000);
}
function bytes(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(1).replace(".", ",") + " Go";
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(".", ",") + " Mo";
  return Math.max(1, Math.round(n / 1e3)) + " Ko";
}
function toast(message) {
  const el = h("div", { class: "toast", role: "status", text: message });
  document.body.append(el);
  setTimeout(() => el.remove(), 3800);
}
function ago(value) {
  const s = (Date.now() - new Date(value)) / 1000;
  if (s < 90) return "à l'instant";
  if (s < 3600) return "il y a " + Math.round(s / 60) + " min";
  return fmtTime.format(new Date(value));
}

const STATUS = {
  queued: ["En attente", "inf"], running: ["En cours", "acc"], succeeded: ["Terminée", "ok"],
  failed: ["Échec", "bad"], cancelled: ["Arrêtée", "warn"],
};
const RUN_STATUS = { ok: "ok", partial: "warn", error: "bad", failed: "bad", running: "acc", interrupted: "bad" };
const RISK = { lecture: ["Lecture seule", "green"], modifie: ["Modifie les données", ""], irreversible: ["Irréversible", "red"] };
function statusPill(status) { const [label, kind] = STATUS[status] || [status, ""]; return pill(label, kind, status === "running"); }
function card(title, ...children) {
  return h("section", { class: "card" }, title ? h("h2", {}, ...[].concat(title)) : null, ...children);
}
function familyIcon(family, size) {
  return h("span", { class: "icon fam-" + family, style: size ? `width:${size}px;height:${size}px` : null }, icon(FAMILY_ICON[family] || "i-bolt"));
}

// Anneau de jauge (SVG).
function ring(fraction, label, color) {
  const c = 2 * Math.PI * 15;
  const id = "g" + Math.random().toString(36).slice(2, 8);
  const grad = svgEl("linearGradient", { id }, svgEl("stop", { offset: "0", "stop-color": "#7c3aed" }), svgEl("stop", { offset: "1", "stop-color": "#b793f5" }));
  const value = Math.min(1, Math.max(0, fraction || 0));
  return svgEl("svg", { class: "ring", viewBox: "0 0 36 36" },
    svgEl("defs", {}, grad),
    svgEl("circle", { cx: 18, cy: 18, r: 15, fill: "none", stroke: "rgba(255,255,255,.07)", "stroke-width": 4 }),
    svgEl("circle", { cx: 18, cy: 18, r: 15, fill: "none", stroke: color || `url(#${id})`, "stroke-width": 4, "stroke-linecap": "round", "stroke-dasharray": `${(value * c).toFixed(1)} ${c.toFixed(1)}`, transform: "rotate(-90 18 18)" }),
    svgEl("text", { x: 18, y: 21.3, "text-anchor": "middle" }, label));
}
function sparkline(values) {
  const max = Math.max(...values, 1); const min = Math.min(...values, 0);
  const span = Math.max(max - min, 1);
  const pts = values.map((v, i) => [(i / Math.max(values.length - 1, 1)) * 200, 40 - ((v - min) / span) * 34]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const id = "s" + Math.random().toString(36).slice(2, 8);
  return svgEl("svg", { class: "spark", viewBox: "0 0 200 44", preserveAspectRatio: "none" },
    svgEl("defs", {}, svgEl("linearGradient", { id, x1: 0, x2: 0, y1: 0, y2: 1 },
      svgEl("stop", { offset: "0", "stop-color": "#b793f5", "stop-opacity": ".45" }),
      svgEl("stop", { offset: "1", "stop-color": "#b793f5", "stop-opacity": "0" }))),
    svgEl("path", { d: line + " L200 44 L0 44Z", fill: `url(#${id})` }),
    svgEl("path", { d: line, fill: "none", stroke: "#b793f5", "stroke-width": 2 }));
}
function bar(fraction) {
  const b = h("div", { class: "bar" }, h("i"));
  b.firstChild.style.width = Math.round(Math.min(1, Math.max(0, fraction || 0)) * 100) + "%";
  return b;
}

async function getCatalog() {
  if (!catalog) catalog = await api("GET", CONSOLE + "/actions");
  return catalog;
}

// --- Fenêtres (confirmation, saisie, secret) -----------------------------------

function modal(build) {
  const root = document.getElementById("modal");
  return new Promise((resolve) => {
    const close = (value) => { root.hidden = true; root.replaceChildren(); resolve(value); };
    root.replaceChildren(h("div", { class: "modal-box", role: "dialog" }, ...build(close)));
    root.hidden = false;
    root.onclick = (e) => { if (e.target === root) close(null); };
    const input = root.querySelector("input"); if (input) input.focus();
  });
}
function confirmBox(title, text, okLabel, danger) {
  return modal((close) => [h("h3", { text: title }), h("p", { text }),
    h("div", { class: "btns" }, h("button", { class: "btn" + (danger ? " danger" : ""), type: "button", text: okLabel || "Confirmer", onclick: () => close(true) }),
      h("button", { class: "btn ghost", type: "button", text: "Annuler", onclick: () => close(false) }))]);
}
function promptBox(title, text, placeholder) {
  return modal((close) => {
    const input = h("input", { class: "input", type: "text", placeholder: placeholder || "" });
    const form = h("form", { onsubmit: (e) => { e.preventDefault(); close(input.value.trim() || null); } }, input,
      h("div", { class: "btns", style: "margin-top:12px" }, h("button", { class: "btn", type: "submit", text: "Valider" }),
        h("button", { class: "btn ghost", type: "button", text: "Annuler", onclick: () => close(null) })));
    return [h("h3", { text: title }), h("p", { text }), form];
  });
}
function secretBox(title, text, secret) {
  return modal((close) => [h("h3", { text: title }), h("p", { text }), h("div", { class: "secret", text: secret }),
    h("div", { class: "btns" }, h("button", { class: "btn", type: "button", onclick: async () => {
      try { await navigator.clipboard.writeText(secret); toast("Copié."); } catch { toast("Copie impossible : sélectionne le texte."); }
    } }, icon("i-copy"), "Copier"), h("button", { class: "btn ghost", type: "button", text: "Fermer", onclick: () => close(true) }))]);
}

// --- Connexion --------------------------------------------------------------------

function showLogin(message) {
  document.getElementById("shell").hidden = true;
  document.getElementById("login").hidden = false;
  const error = document.getElementById("login-error");
  error.hidden = !message;
  error.textContent = message || "";
}
function logout() {
  if (token) {
    // Session fermée côté serveur : le jeton ne sert plus, même copié ailleurs.
    fetch(API + CONSOLE + "/logout", { method: "POST", headers: { Authorization: "Bearer " + token } }).catch(() => {});
  }
  token = null; me = null; catalog = null; writeToken(null); stopTimer(); codeStep(false); showLogin();
}
function otpInputs() { return [...document.querySelectorAll("#login-code .otp input")]; }
function codeStep(on) {
  document.getElementById("login-creds").hidden = on;
  document.getElementById("login-code").hidden = !on;
  document.getElementById("login-submit").textContent = on ? "Vérifier et entrer" : "Se connecter";
  for (const input of otpInputs()) input.value = "";
  if (on) otpInputs()[0].focus();
}
function otpValue() { return otpInputs().map((i) => i.value).join(""); }
function wireOtp() {
  const inputs = otpInputs();
  inputs.forEach((input, i) => {
    input.addEventListener("input", () => {
      const digits = input.value.replace(/\D/g, "");
      if (digits.length > 1) { // code collé ou proposé par le téléphone
        digits.slice(0, 6).split("").forEach((d, k) => { if (inputs[k]) inputs[k].value = d; });
        inputs[Math.min(digits.length, 6) - 1].focus();
      } else {
        input.value = digits;
        if (digits && inputs[i + 1]) inputs[i + 1].focus();
      }
      if (otpValue().length === 6) document.getElementById("login-form").requestSubmit();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !input.value && inputs[i - 1]) inputs[i - 1].focus();
    });
  });
}
async function login(event) {
  event.preventDefault();
  const form = event.target;
  const button = document.getElementById("login-submit");
  const phone = form.phone.value.trim();
  const withCode = !document.getElementById("login-code").hidden;
  if (!phone.startsWith("+") && !phone.startsWith("00")) {
    showLogin("Numéro sans indicatif : écris-le avec l'indicatif du pays, ex. +225 " + phone);
    return;
  }
  const body = { phone, password: form.password.value };
  if (withCode) {
    body.code = otpValue();
    if (body.code.length !== 6) { showLogin("Entre les 6 chiffres du code."); return; }
  }
  button.disabled = true;
  try {
    const data = await api("POST", "/auth/console-login", body);
    token = data.access_token;
    await start();
    if (me) { writeToken(token); form.password.value = ""; codeStep(false); }
  } catch (err) {
    if (err.code === "totp_required") { showLogin(); codeStep(true); }
    else {
      showLogin(err.message);
      if (withCode) { for (const input of otpInputs()) input.value = ""; otpInputs()[0].focus(); }
    }
  } finally {
    button.disabled = false;
  }
}
async function start() {
  try { me = await api("GET", CONSOLE + "/me"); } catch (err) { token = null; showLogin(err.status === 401 ? null : err.message); return; }
  document.getElementById("login").hidden = true;
  document.getElementById("shell").hidden = false;
  document.getElementById("me-name").textContent = me.display_name;
  document.getElementById("me-avatar").textContent = me.display_name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  document.getElementById("nav-security").hidden = !!me.totp_enabled;
  route();
}

// --- Navigation -----------------------------------------------------------------

function stopTimer() { if (timer) clearTimeout(timer); timer = null; }
function setPage(page, title) {
  document.getElementById("title").textContent = title;
  document.title = "FootProba · " + title;
  for (const a of document.querySelectorAll("#nav a, #tabbar a")) a.classList.toggle("on", a.dataset.page === page);
}
function setStatus(text, kind) {
  const el = document.getElementById("status");
  el.className = "pill " + (kind || "");
  el.replaceChildren(h("i"), text || "");
  el.hidden = !text;
}
function view(...children) {
  const el = document.getElementById("view");
  el.replaceChildren(...children);
  window.scrollTo(0, 0);
  return el;
}
async function route() {
  stopTimer();
  setStatus("");
  closePalette();
  if (!me) return;
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  try {
    if (parts[0] === "actions" && parts[1]) await actionForm(parts[1]);
    else if (parts[0] === "actions") await actionsPage();
    else if (parts[0] === "journal") await journalPage();
    else if (parts[0] === "jobs" && parts[1]) await jobPage(Number(parts[1]));
    else if (parts[0] === "fichiers") await filesPage();
    else if (parts[0] === "codes") await codesPage();
    else if (parts[0] === "comptes") await accountsPage();
    else if (parts[0] === "paiements") await paymentsPage();
    else if (parts[0] === "versions") await versionsPage();
    else if (parts[0] === "securite") await securityPage();
    else if (parts[0] === "plus") plusPage();
    else await dashboardPage();
  } catch (err) {
    if (err.status !== 401) view(card("Erreur", h("p", { class: "error", text: err.message })));
  }
}

// --- Tableau de bord ---------------------------------------------------------------

function timeline(runs, jobs) {
  const now = Date.now(); const start = now - 86400000;
  const rows = runs.map((task) => {
    const track = h("div", { class: "track" });
    for (const run of task.runs) {
      const t = new Date(run.at).getTime();
      const b = h("b", { class: run.status, title: `${when(run.at)} · ${duration(run.seconds)} · ${run.status}` });
      b.style.left = (((t - start) / 86400000) * 100).toFixed(2) + "%";
      b.style.width = Math.max((run.seconds / 86400) * 100, 0.35).toFixed(2) + "%";
      track.append(b);
    }
    const last = task.runs[0];
    return h("div", { class: "tl" }, h("span", { class: "lbl", text: task.label }), track,
      h("span", { class: "last", text: last ? ago(last.at) : "—" }));
  });
  for (const job of jobs.filter((j) => j.status === "running" && j.started_at)) {
    const track = h("div", { class: "track" });
    const b = h("b", { class: "running" });
    const t = Math.max(new Date(job.started_at).getTime(), start);
    b.style.left = (((t - start) / 86400000) * 100).toFixed(2) + "%";
    b.style.width = Math.max(((now - t) / 86400000) * 100, 0.6).toFixed(2) + "%";
    track.append(b);
    rows.push(h("div", { class: "tl" }, h("span", { class: "lbl", text: job.title }), track, h("span", { class: "last", text: "en cours" })));
  }
  if (!rows.length) return [h("div", { class: "empty", text: "Aucune exécution enregistrée pour l'instant (les tâches s'inscrivent ici à leur prochain passage)." })];
  const hours = h("div", { class: "hours" }, h("span"), h("div", {}, ...["−24h", "−18h", "−12h", "−6h", "maint."].map((t) => h("span", { text: t }))), h("span"));
  return [...rows, hours];
}

async function dashboardPage() {
  setPage("dashboard", "Tableau de bord");
  const d = await api("GET", CONSOLE + "/dashboard");
  lastDashboard = d;
  const s = d.services;
  const allOk = s.database && s.redis && s.workers > 0;
  setStatus(allOk ? "Tout fonctionne" : "Un service ne répond pas", allOk ? "ok" : "bad");
  const hour = new Date().getHours();
  document.getElementById("title").textContent = (hour < 18 ? "Bonjour " : "Bonsoir ") + me.display_name.split(" ")[0];
  updateBadges(d);

  const q = d.quota;
  const quotaCard = q && q.limit
    ? h("div", { class: "card kpi" }, ring(q.used / q.limit, Math.round((q.used / q.limit) * 100) + "%"),
      h("div", {}, h("div", { class: "k", text: "API-Football" }), h("div", { class: "v", text: number(q.limit - q.used) }), h("div", { class: "s", text: "restantes sur " + number(q.limit) })))
    : h("div", { class: "card kpi" }, ring(0, "—"), h("div", {}, h("div", { class: "k", text: "API-Football" }), h("div", { class: "v", text: "—" }), h("div", { class: "s", text: "quota indisponible" })));
  const disk = d.disk;
  const used = disk ? 1 - disk.free_gb / disk.total_gb : 0;
  const backup = d.backup;
  const kpis = h("div", { class: "kpis" },
    h("div", { class: "card kpi" }, ring(allOk ? 1 : 0.5, allOk ? "OK" : "!", allOk ? "#34d399" : "#f472b6"),
      h("div", {}, h("div", { class: "k", text: "Services" }), h("div", { class: "v", text: allOk ? "En marche" : "À vérifier" }),
        h("div", { class: "s", text: (s.redis ? "Redis ✓" : "Redis ✗") + " · " + (s.workers ? "worker ✓" : "worker ✗") + (backup ? " · sauvegarde " + ago(backup.at) : "") }))),
    quotaCard,
    h("div", { class: "card kpi" }, ring(used, Math.round(used * 100) + "%", "#7fb7ff"),
      h("div", {}, h("div", { class: "k", text: "Disque" }), h("div", { class: "v", text: disk ? String(disk.free_gb).replace(".", ",") + " Go" : "—" }), h("div", { class: "s", text: disk ? "libres sur " + disk.total_gb + " Go" : "" }))),
    h("div", { class: "card kpi", style: "display:block" }, h("div", { class: "k", text: "Comptes" }),
      h("div", { class: "btns" }, h("div", { class: "v", text: number(d.users.total) }), d.users.new_7d ? pill("+" + d.users.new_7d + " · 7 j", "ok") : null),
      sparkline(d.users.trend || [d.users.total]), h("div", { class: "s", text: "dont " + number(d.users.premium) + " Premium" })));

  const todo = d.todo.length ? d.todo.map((t) => {
    const kind = { error: "bad", warning: "warn", info: "inf" }[t.level];
    const ic = { error: "i-warn", warning: "i-warn", info: "i-card" }[t.level];
    let go = null;
    if (t.action) go = h("button", { class: "btn sm ghost", type: "button", text: "Lancer", onclick: () => { location.hash = "#/actions/" + t.action; } });
    if (t.link === "codes") go = h("button", { class: "btn sm", type: "button", text: "Saisir", onclick: () => { location.hash = "#/codes"; } });
    return h("div", { class: "todo" }, h("span", { class: "ic " + kind }, icon(t.link === "codes" ? "i-ticket" : ic)), h("p", { text: t.text }), go);
  }) : [h("div", { class: "empty", text: "Rien à traiter." })];

  const running = d.jobs.filter((j) => j.status === "running" || j.status === "queued");
  const runningRows = running.length ? running.map((j) => h("div", { class: "job link", onclick: () => { location.hash = "#/jobs/" + j.id; } },
    h("div", { style: "flex:1;min-width:0" }, h("div", { class: "t", text: j.title }), h("small", { text: j.status === "queued" ? "en attente du worker" : (j.eta_seconds ? "reste ≈ " + duration(j.eta_seconds) : "démarrée " + ago(j.started_at)) })),
    bar(j.progress), h("span", { class: "note", text: j.progress ? Math.round(j.progress * 100) + " %" : "" }))) : [h("div", { class: "empty", text: "Aucune tâche en cours." })];

  const recent = d.jobs.slice(0, 6).map((j) => h("div", { class: "row link", onclick: () => { location.hash = "#/jobs/" + j.id; } },
    h("span", {}, j.title), h("span", { class: "t", text: when(j.created_at) }), statusPill(j.status)));

  const lastRuns = [
    ["Ingestion", d.last.ingestion], ["Pronostics", d.last.prediction],
  ].map(([label, run]) => h("div", { class: "row" }, h("span", { text: label }),
    h("span", { class: "t", text: run ? when(run.started_at) + (run.finished_at ? " · " + between(run.started_at, run.finished_at) : "") : "jamais" }),
    run ? pill(run.status, RUN_STATUS[run.status]) : pill("—")));
  lastRuns.push(h("div", { class: "row" }, h("span", { text: "Cotes" }), h("span", { class: "t", text: d.last.odds_at ? when(d.last.odds_at) : "jamais" }), pill(d.last.odds_at ? "relevées" : "—", d.last.odds_at ? "ok" : "")));
  if (d.quality) lastRuns.push(h("div", { class: "row" }, h("span", { text: "Qualité" }), h("span", { class: "t", text: `${d.quality.errors} erreur(s), ${d.quality.warnings} avert.` }), pill(d.quality.errors ? "erreurs" : "ok", d.quality.errors ? "bad" : "ok")));
  lastRuns.push(h("div", { class: "row link", onclick: () => { location.hash = "#/codes"; } }, h("span", { text: "Coupons du jour" }), h("span", { class: "t", text: d.coupons_today.count + " créé(s)" }),
    d.coupons_today.missing_codes.length ? pill("codes à saisir", "warn") : pill(d.coupons_today.count ? "OK" : "—", d.coupons_today.count ? "ok" : "")));

  view(kpis,
    h("div", { class: "grid-2" },
      card(["Tâches automatiques", h("small", { text: "dernières 24 h" })], ...timeline(d.runs || [], d.jobs)),
      h("div", { style: "display:grid;gap:12px;align-content:start" },
        card(["À traiter", d.todo.length ? pill(String(d.todo.length), "warn") : pill("0", "ok")], ...todo),
        card("En cours", ...runningRows))),
    h("div", { class: "grid-2e" },
      card("Dernières exécutions", ...lastRuns),
      card(["Dernières actions", h("a", { href: "#/journal", class: "small", text: "Tout le journal" })], ...(recent.length ? recent : [h("div", { class: "empty", text: "Aucune action lancée depuis la console." })]))));
  timer = setTimeout(route, 30000);
}

function updateBadges(d) {
  const codes = document.getElementById("nav-codes");
  codes.hidden = !d.coupons_today.missing_codes.length;
  codes.textContent = d.coupons_today.missing_codes.length;
  const run = document.getElementById("nav-running");
  const n = d.jobs.filter((j) => j.status === "running").length;
  run.hidden = !n; run.textContent = n; run.classList.add("run");
}

// --- Palette Ctrl K ----------------------------------------------------------------

let paletteItems = [];
let paletteIndex = 0;
async function openPalette() {
  const box = document.getElementById("palette");
  box.hidden = false;
  const input = document.getElementById("palette-input");
  input.value = "";
  input.focus();
  renderPalette("");
  try { await getCatalog(); } catch { /* catalogue indisponible : pages seulement */ }
  renderPalette(input.value); // la saisie a pu commencer pendant le chargement
}
function closePalette() { document.getElementById("palette").hidden = true; }
function renderPalette(query) {
  const q = query.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const norm = (t) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const actions = (catalog || []).filter((a) => !q || norm(a.title + " " + a.description + " " + a.family).includes(q))
    .map((a) => ({ label: a.title, sub: a.family + (a.cost ? " · " + a.cost : ""), family: a.family, go: () => { location.hash = "#/actions/" + a.id; } }));
  const pages = PAGES.filter((p) => !q || norm(p.title).includes(q))
    .map((p) => ({ label: p.title, sub: "Page", iconName: p.icon, go: () => { location.hash = p.hash; } }));
  paletteItems = [...actions, ...pages].slice(0, 30);
  paletteIndex = 0;
  drawPalette();
}
function drawPalette() {
  const list = document.getElementById("palette-list");
  list.replaceChildren(...(paletteItems.length ? paletteItems.map((item, i) => h("div", {
    class: "palette-item" + (i === paletteIndex ? " on" : ""), onclick: () => { closePalette(); item.go(); },
  }, item.family ? familyIcon(item.family) : h("span", { class: "icon mute" }, icon(item.iconName)), h("div", {}, item.label, h("small", { text: item.sub })))) : [h("div", { class: "empty", style: "padding:14px", text: "Aucun résultat." })]));
}

// --- Actions -----------------------------------------------------------------------

let familyFilter = "Toutes";
let textFilter = "";
function actionTags(a) {
  const [riskLabel, riskKind] = RISK[a.risk] || [a.risk, ""];
  return h("div", { class: "meta" },
    a.cost ? h("span", { class: "tag" }, icon("i-coin"), a.cost) : null,
    a.duration ? h("span", { class: "tag" }, icon("i-clock"), a.duration) : null,
    h("span", { class: "tag " + riskKind }, icon("i-shield"), riskLabel),
    a.exclusive ? h("span", { class: "tag", text: "une à la fois" }) : null,
    a.produces_file ? h("span", { class: "tag" }, icon("i-file"), "fichier") : null,
    a.stoppable ? h("span", { class: "tag", text: "arrêtable" }) : null);
}
async function actionsPage() {
  setPage("actions", "Actions");
  const actions = await getCatalog();
  const families = ["Toutes", ...new Set(actions.map((a) => a.family))];
  const counts = Object.fromEntries(families.map((f) => [f, f === "Toutes" ? actions.length : actions.filter((a) => a.family === f).length]));
  const list = h("div", { class: "acts" });
  const fam = h("div", { class: "fam" });
  const filter = h("input", { class: "input filter", type: "search", placeholder: "Filtrer…", value: textFilter, oninput: (e) => { textFilter = e.target.value; render(); } });
  function render() {
    fam.replaceChildren(...families.map((f) => h("button", { class: "f" + (f === familyFilter ? " on" : ""), type: "button", onclick: () => { familyFilter = f; render(); } }, f, h("b", { text: counts[f] }))));
    const t = textFilter.toLowerCase();
    const shown = actions.filter((a) => (familyFilter === "Toutes" || a.family === familyFilter) && (!t || (a.title + " " + a.description).toLowerCase().includes(t)));
    list.replaceChildren(...(shown.length ? shown.map((a) => h("button", { class: "act", type: "button", onclick: () => { location.hash = "#/actions/" + a.id; } },
      h("div", { class: "head" }, familyIcon(a.family), h("div", { class: "ttl", text: a.title })),
      h("div", { class: "d", text: a.description }), actionTags(a))) : [h("div", { class: "empty", text: "Aucune action." })]));
  }
  render();
  view(h("div", { class: "toolbar" }, fam, filter), list,
    h("p", { class: "note", style: "margin-top:14px", text: "Le catalogue vient du serveur : une nouvelle action apparaît ici dès la mise à jour du serveur." }));
}

function paramField(p, initial, onChange) {
  const value = initial === undefined ? p.default : initial;
  const wrap = h("div", { class: "field" });
  const label = h("label", { text: p.label });
  let read;
  if (p.kind === "choices") {
    const chosen = new Set(value || []);
    const chips = h("div", { class: "chips" });
    const render = () => { chips.replaceChildren(...p.options.map((o) => h("button", {
      class: "chip" + (chosen.has(o.value) ? " on" : ""), type: "button", text: o.label, "aria-pressed": chosen.has(o.value) ? "true" : "false",
      onclick: () => { chosen.has(o.value) ? chosen.delete(o.value) : chosen.add(o.value); render(); onChange(); },
    }))); };
    render();
    const tools = h("div", { class: "chip-tools" },
      h("button", { class: "btn sm ghost", type: "button", text: "Tout", onclick: () => { p.options.forEach((o) => chosen.add(o.value)); render(); onChange(); } }),
      h("button", { class: "btn sm ghost", type: "button", text: "Aucun", onclick: () => { chosen.clear(); render(); onChange(); } }),
      h("span", { class: "note", style: "align-self:center" }));
    wrap.append(label, tools, chips);
    read = () => p.options.map((o) => o.value).filter((v) => chosen.has(v));
  } else if (p.kind === "choice") {
    const select = h("select", { class: "input", onchange: onChange }, ...p.options.map((o) => h("option", { value: o.value, text: o.label, selected: o.value === value })));
    wrap.append(label, select);
    read = () => select.value;
  } else if (p.kind === "int") {
    const input = h("input", { type: "number", step: "1", min: p.min, max: p.max, value: value ?? "", oninput: onChange });
    const bump = (d) => { const n = Number(input.value || 0) + d; input.value = String(p.min !== undefined ? Math.max(p.min, n) : n); onChange(); };
    const stepSize = (p.default || 0) >= 500 ? 100 : 1;
    wrap.append(label, h("div", { class: "stepper" }, h("button", { type: "button", text: "−", onclick: () => bump(-stepSize) }), input, h("button", { type: "button", text: "+", onclick: () => bump(stepSize) })));
    read = () => (input.value === "" ? null : Number(input.value));
  } else if (p.kind === "bool") {
    let on = !!value;
    const t = h("button", { class: "toggle", type: "button", role: "switch", "aria-checked": String(on) }, h("span", { class: "sw" }), p.label);
    t.addEventListener("click", () => { on = !on; t.setAttribute("aria-checked", String(on)); onChange(); });
    wrap.append(t);
    read = () => on;
  } else {
    const input = h("input", { class: "input", type: "text", maxlength: "200", value: value ?? "", oninput: onChange });
    wrap.append(label, input);
    read = () => input.value;
  }
  if (p.help) wrap.append(h("p", { class: "help", text: p.help }));
  return { el: wrap, read };
}

async function actionForm(actionId) {
  setPage("actions", "Actions");
  const actions = await getCatalog();
  const a = actions.find((x) => x.id === actionId);
  if (!a) { view(card("Action inconnue", h("p", { class: "muted", text: "Cette action n'existe pas (ou plus) sur ce serveur." }))); return; }
  document.getElementById("title").textContent = a.title;
  const initial = prefill && prefill.action === a.id ? prefill.params : {};
  prefill = null;
  const summary = h("div");
  const fields = a.params.map((p) => ({ p, ...paramField(p, initial[p.name], () => renderSummary()) }));
  let confirmed = false;
  const confirmEl = a.confirm ? h("label", { class: "confirm" }, h("input", { type: "checkbox", onchange: (e) => { confirmed = e.target.checked; } }), "Je confirme : cette action est irréversible.") : null;
  const error = h("p", { class: "error", hidden: true });
  const launch = h("button", { class: "btn wide", type: "button" }, icon("i-bolt"), "Lancer");
  const quota = (lastDashboard && lastDashboard.quota) || null;

  function renderSummary() {
    const rows = [];
    for (const f of fields) {
      if (f.p.kind === "choices") rows.push([f.p.label, String(f.read().length) + " / " + f.p.options.length]);
    }
    const [riskLabel] = RISK[a.risk] || [a.risk];
    rows.push(["Risque", riskLabel], ["Coût", a.cost || "—"], ["Durée", a.duration || "—"]);
    if (a.produces_file) rows.push(["Résultat", "fichier (page Fichiers)"]);
    const parts = rows.map(([k, v]) => h("div", { class: "row" }, h("span", { text: k }), h("b", { text: v })));
    if (quota && quota.limit && /requ/.test(a.cost || "") && !/aucune/.test(a.cost || "")) {
      const usedPct = (quota.used / quota.limit) * 100;
      const q = h("div", { class: "quota" }, h("i", { class: "u" }), h("i", { class: "r" }));
      q.children[0].style.width = usedPct.toFixed(1) + "%";
      q.children[1].style.width = (100 - usedPct).toFixed(1) + "%";
      parts.push(h("div", { class: "row" }, h("span", { text: "Quota restant aujourd'hui" }), h("b", { text: number(quota.limit - quota.used) })), q,
        h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:rgba(244,242,248,.45)" }), "utilisé"), h("span", {}, h("i", { style: "background:rgba(52,211,153,.5)" }), "disponible")));
    }
    if (a.steps.length) parts.push(h("ul", { class: "steps" }, ...a.steps.map((s) => h("li", {}, h("span", { class: "dot" }), s))));
    summary.replaceChildren(...parts);
  }
  renderSummary();

  launch.addEventListener("click", async () => {
    error.hidden = true;
    if (a.confirm && !confirmed) { error.textContent = "Coche la confirmation : cette action est irréversible."; error.hidden = false; return; }
    const params = {};
    for (const f of fields) params[f.p.name] = f.read();
    launch.disabled = true;
    try {
      const job = await api("POST", CONSOLE + "/jobs", { action: a.id, params, confirmed: !!a.confirm });
      location.hash = "#/jobs/" + job.id;
    } catch (err) {
      error.textContent = err.message; error.hidden = false; launch.disabled = false;
    }
  });

  view(h("div", { class: "toolbar" }, h("a", { href: "#/actions", class: "small", text: "← Toutes les actions" }), pill(a.family, "acc")),
    h("div", { class: "form-wrap" },
      card(null, h("div", { class: "btns", style: "margin-bottom:14px;flex-wrap:nowrap;align-items:flex-start" }, familyIcon(a.family), h("p", { class: "muted", style: "margin:0", text: a.description })),
        ...(fields.length ? fields.map((f) => f.el) : [h("p", { class: "note", text: "Aucun réglage : l'action se lance telle quelle." })]), confirmEl),
      h("div", { class: "card sum" }, h("h2", { text: "Récapitulatif" }), summary, h("div", { style: "margin-top:14px" }, error, launch))));
}

// --- Journal et suivi ----------------------------------------------------------------

async function journalPage() {
  setPage("journal", "Journal");
  const jobs = await api("GET", CONSOLE + "/jobs?limit=100");
  const body = jobs.length ? jobs.map((j) => h("tr", { class: "link", onclick: () => { location.hash = "#/jobs/" + j.id; } },
    h("td", { class: "mono hide-sm", text: "n°" + j.id }), h("td", {}, j.title, h("div", { class: "note", text: j.summary || "" })),
    h("td", {}, statusPill(j.status)), h("td", { class: "hide-sm", text: when(j.created_at) }), h("td", { class: "hide-sm", text: between(j.started_at, j.finished_at) })))
    : [h("tr", {}, h("td", { colspan: "5", class: "empty", text: "Aucune action lancée." }))];
  view(card(null, h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", { class: "hide-sm", text: "" }), h("th", { text: "Action" }), h("th", { text: "État" }), h("th", { class: "hide-sm", text: "Lancée" }), h("th", { class: "hide-sm", text: "Durée" }))),
    h("tbody", {}, ...body)))));
  timer = setTimeout(route, 15000);
}

function logLine(line) {
  const text = line.text || " ";
  let cls = null;
  if (/^(Erreur|erreur|échec|.*Error:|.*erreur \{)/.test(text.trim()) || /: erreur /.test(text)) cls = "r";
  else if (/^Fin :|terminé|prête|prêt :|✓/.test(text.trim())) cls = "g";
  else if (/attention|limite|pause|avertissement|warning/i.test(text)) cls = "y";
  else if (/^== |^\$ |^Démarrage/.test(text.trim())) cls = "p";
  const time = new Date(line.at);
  return h("div", { class: cls === "r" ? "has-r" : null }, h("span", { class: "t", text: fmtTime.format(time) + "  " }), h("span", { class: cls, text }));
}

async function jobPage(jobId) {
  setPage("journal", "Tâche n°" + jobId);
  let last = 0;
  let errorsOnly = false;
  const actions = await getCatalog();
  const log = h("div", { class: "log", "aria-live": "polite" });
  const count = h("span", { text: "Journal" });
  const all = h("button", { class: "pill acc", type: "button", text: "Tout", onclick: () => { errorsOnly = false; filterLog(); } });
  const errs = h("button", { class: "pill mute", type: "button", text: "Erreurs", onclick: () => { errorsOnly = true; filterLog(); } });
  const copy = h("button", { class: "pill mute", type: "button", onclick: async () => {
    try { await navigator.clipboard.writeText(log.innerText); toast("Journal copié."); } catch { toast("Copie impossible."); }
  } }, "Copier");
  function filterLog() {
    log.classList.toggle("errors-only", errorsOnly);
    all.className = "pill " + (errorsOnly ? "mute" : "acc");
    errs.className = "pill " + (errorsOnly ? "bad" : "mute");
  }
  const head = h("div");
  let lines = 0; let errorCount = 0;

  function renderHead(job) {
    const a = actions.find((x) => x.id === job.action);
    document.getElementById("title").textContent = job.title;
    const active = job.status === "queued" || job.status === "running";
    const pct = job.status === "succeeded" ? 1 : (job.progress || 0);
    const steps = a && a.steps.length ? h("ul", { class: "steps" }, ...a.steps.map((s, i) => {
      const cur = job.step ?? -1;
      const state = job.status === "succeeded" || i < cur ? "done" : (i === cur && active ? "cur" : "");
      return h("li", { class: state }, h("span", { class: "dot" }, state === "done" ? icon("i-check") : null), s);
    })) : null;
    const params = Object.entries(job.params || {}).map(([k, v]) => {
      const p = a && a.params.find((x) => x.name === k);
      const shown = Array.isArray(v) ? (v.length > 5 ? v.length + " choisis" : v.join(", ")) : (typeof v === "boolean" ? (v ? "oui" : "non") : String(v === "" ? "défaut" : v));
      return h("div", { class: "row" }, h("span", { class: "t", text: p ? p.label : k }), h("b", { class: "small", text: shown }));
    });
    const buttons = [];
    if (active && (job.status === "queued" || (a && a.stoppable)) && !job.stop_requested) {
      buttons.push(h("button", { class: "btn sm danger", type: "button", text: "Arrêter", onclick: () => stop(job.id) }));
    }
    if (job.stop_requested && active) buttons.push(pill("arrêt demandé…", "warn"));
    if (!active && a) {
      buttons.push(h("button", { class: "btn sm ghost", type: "button", text: "Relancer avec les mêmes réglages", onclick: () => { prefill = { action: a.id, params: job.params }; location.hash = "#/actions/" + a.id; } }));
    }
    if (!active && a && a.produces_file && job.status === "succeeded") buttons.push(h("a", { class: "btn sm", href: "#/fichiers" }, icon("i-down"), "Fichiers"));
    const silent = job.silent_seconds && job.silent_seconds > 180 ? h("p", { class: "note", text: "Aucun signe de vie depuis " + duration(job.silent_seconds) + " (calcul long, ou serveur redémarré)." }) : null;
    head.replaceChildren(h("section", { class: "card" },
      h("div", { class: "btns", style: "justify-content:space-between" }, h("span", { class: "note", text: "Progression" }), statusPill(job.status)),
      h("div", { class: "big", text: Math.round(pct * 100) + " %" }),
      h("div", { style: "margin:10px 0 6px" }, bar(pct)),
      h("div", { class: "note", text: active ? (job.eta_seconds ? "reste ≈ " + duration(job.eta_seconds) : "démarrée " + (job.started_at ? ago(job.started_at) : "bientôt")) : "durée " + between(job.started_at, job.finished_at) }),
      job.summary ? h("p", { style: "margin:12px 0 0", text: job.summary }) : null,
      steps, silent,
      params.length ? h("div", { style: "margin-top:12px" }, ...params) : null,
      buttons.length ? h("div", { class: "btns", style: "margin-top:14px" }, ...buttons) : null));
    setStatus(STATUS[job.status] ? STATUS[job.status][0] : job.status, STATUS[job.status] ? STATUS[job.status][1] : "");
  }
  async function stop(id) {
    if (!(await confirmBox("Arrêter la tâche ?", "Ce qui est déjà fait est gardé ; la tâche s'arrête à la prochaine étape sûre.", "Arrêter", true))) return;
    try { await api("POST", `${CONSOLE}/jobs/${id}/stop`); toast("Arrêt demandé."); poll(); } catch (err) { toast(err.message); }
  }
  async function poll() {
    stopTimer();
    const job = await api("GET", `${CONSOLE}/jobs/${jobId}?after=${last}`);
    renderHead(job);
    if (job.lines.length) {
      const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
      for (const line of job.lines) {
        const row = logLine(line);
        if (row.classList.contains("has-r")) errorCount += 1;
        log.append(row); last = line.n; lines += 1;
      }
      count.textContent = "Journal · " + number(lines) + " lignes";
      errs.textContent = "Erreurs (" + errorCount + ")";
      if (atBottom) log.scrollTop = log.scrollHeight;
    }
    if (job.status === "queued" || job.status === "running" || job.lines.length === 1000) {
      timer = setTimeout(() => poll().catch(() => { timer = setTimeout(poll, POLL_MS * 4); }), POLL_MS);
    }
  }
  view(h("div", { class: "follow" }, head, h("div", { class: "term" },
    h("div", { class: "term-bar" }, h("span", { class: "dots" }, h("i"), h("i"), h("i")), count, h("span", { class: "sp" }, all, errs, copy)), log)));
  await poll();
}

// --- Fichiers ----------------------------------------------------------------------

async function filesPage() {
  setPage("fichiers", "Fichiers");
  const list = await api("GET", CONSOLE + "/files");
  async function download(name) {
    try { const { url } = await api("POST", `${CONSOLE}/files/${encodeURIComponent(name)}/link`); location.href = url; }
    catch (err) { toast(err.message); }
  }
  async function remove(name) {
    if (!(await confirmBox("Supprimer ce fichier ?", name, "Supprimer", true))) return;
    try { await api("DELETE", `${CONSOLE}/files/${encodeURIComponent(name)}`); toast("Fichier supprimé."); filesPage(); } catch (err) { toast(err.message); }
  }
  const iconFor = (n) => (n.endsWith(".dump") ? "i-db" : n.includes("moteur") ? "i-chart" : "i-file");
  const rows = list.map((f) => h("tr", {},
    h("td", {}, h("div", { class: "file" }, h("span", { class: "fi" }, icon(iconFor(f.name))), h("span", { text: f.name }))),
    h("td", { class: "hide-sm", text: bytes(f.size) }), h("td", { class: "hide-sm", text: when(f.modified_at) }),
    h("td", {}, h("div", { class: "acct-tools" },
      h("button", { class: "btn sm", type: "button", onclick: () => download(f.name) }, icon("i-down"), h("span", { class: "hide-sm", text: "Télécharger" })),
      h("button", { class: "icon-btn", type: "button", title: "Supprimer", "aria-label": "Supprimer", onclick: () => remove(f.name) }, icon("i-trash"))))));
  view(h("p", { class: "note", style: "margin:0 0 12px", text: "Exports pour l'étude, archives et rapports produits par les actions, gardés 30 jours. Jamais de donnée personnelle ; les sauvegardes de la base ne sont pas téléchargeables." }),
    card(null, list.length ? h("div", { class: "scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", { text: "Fichier" }), h("th", { class: "hide-sm", text: "Taille" }), h("th", { class: "hide-sm", text: "Date" }), h("th"))),
      h("tbody", {}, ...rows))) : h("div", { class: "empty", text: "Aucun fichier. Les actions « Exporter les données », « Évaluer le moteur »… en produisent." })));
}

// --- Codes du jour -------------------------------------------------------------------

const MARKETS = { "1X2": "1X2", OU: "Buts", BTTS: "Les deux marquent", DC: "Double chance" };
function selectionText(s) {
  const market = MARKETS[s.market] || s.market;
  return `${s.home} – ${s.away} · ${market} ${s.selection}${s.line ? " " + s.line : ""} @ ${s.odds}`;
}
async function codesPage() {
  setPage("codes", "Codes du jour");
  const data = await api("GET", "/admin/smart-coupons");
  if (!data.coupons.length) {
    view(card("Coupons du " + data.day, h("p", { class: "muted", text: "Aucun coupon du jour pour l'instant (créés à 08:05, ou action « Créer les coupons du jour »)." })));
    return;
  }
  view(h("p", { class: "note", style: "margin:0 0 12px", text: "Recrée chaque coupon chez 1xBet, puis colle son code de réservation : les joueurs le copient dans l'application. Quand tous les codes sont saisis, la notification « coupons du jour disponibles » part d'elle-même." }),
    h("div", { class: "grid-2e", style: "margin-top:0" }, ...data.coupons.map((c) => {
      const current = (c.booking_codes.find((b) => b.bookmaker === "1xbet") || {}).code || "";
      const input = h("input", { class: "input mono", type: "text", maxlength: "32", value: current, placeholder: "code 1xBet", style: "max-width:200px" });
      const save = h("button", { class: "btn sm", type: "button", text: "Enregistrer", onclick: async () => {
        save.disabled = true;
        try { await api("PUT", `/admin/smart-coupons/${c.id}/booking-code`, { bookmaker: "1xbet", code: input.value }); toast(input.value.trim() ? "Code enregistré." : "Code retiré."); codesPage(); }
        catch (err) { toast(err.message); save.disabled = false; }
      } });
      return card([c.profile_label, current ? pill("code saisi", "ok") : pill("code à saisir", "warn")],
        h("div", { class: "note", text: `${c.selections.length} sélections · cote ${c.total_odds} · probabilité ${Math.round(c.probability * 100)} %` }),
        h("div", { style: "margin:8px 0 12px" }, ...c.selections.map((s) => h("div", { class: "sel", text: selectionText(s) }))),
        h("div", { class: "btns" }, input, save));
    })));
}

// --- Comptes -------------------------------------------------------------------------

async function accountsPage(query) {
  setPage("comptes", "Comptes");
  const q = query === undefined ? "" : query;
  const users = await api("GET", "/admin/users?limit=100" + (q ? "&q=" + encodeURIComponent(q) : ""));
  const search = h("input", { class: "input filter", type: "search", placeholder: "Nom ou numéro", value: q });
  const form = h("form", { class: "toolbar", onsubmit: (e) => { e.preventDefault(); accountsPage(search.value.trim()); } }, search, h("button", { class: "btn", type: "submit" }, icon("i-search"), "Chercher"));
  async function act(title, text, fn, danger) {
    if (!(await confirmBox(title, text, "Confirmer", danger))) return;
    try { await fn(); toast("Fait."); accountsPage(q); } catch (err) { toast(err.message); }
  }
  async function changePhone(u) {
    const phone = await promptBox("Changer le numéro", `Nouveau numéro de connexion de ${u.display_name}, avec l'indicatif.`, "+225 05 00 00 00 00");
    if (!phone) return;
    try { await api("POST", `/admin/users/${u.id}/phone`, { phone }); toast("Numéro changé."); accountsPage(q); } catch (err) { toast(err.message); }
  }
  async function resetPassword(u) {
    if (!(await confirmBox("Mot de passe provisoire", `Un nouveau mot de passe va remplacer celui de ${u.display_name}. Il ne s'affichera qu'une fois.`, "Générer", true))) return;
    try {
      const { password } = await api("POST", `/admin/users/${u.id}/password-reset`);
      await secretBox("Mot de passe provisoire", `À transmettre à ${u.display_name} (${u.phone || u.email || "Google"}). À changer dans l'application : Profil → Changer le mot de passe.`, password);
    } catch (err) { toast(err.message); }
  }
  const rows = users.map((u) => h("tr", {},
    h("td", {}, h("div", { style: "font-weight:600" }, u.display_name, u.role === "admin" ? [" ", pill("admin", "acc")] : null), h("div", { class: "note mono", text: u.phone || ("Google · " + (u.email || "")) })),
    h("td", { class: "hide-sm" }, pill(u.plan, u.plan === "free" ? "" : "ok"), u.premium_until ? h("div", { class: "note", text: "jusqu'au " + fmtDateTime.format(new Date(u.premium_until)) }) : null),
    h("td", { class: "hide-sm" }, u.is_active ? pill("actif", "ok") : pill("désactivé", "bad")),
    h("td", {}, h("div", { class: "acct-tools" },
      h("button", { class: "btn sm", type: "button", text: "+30 j", title: "Offrir 30 jours de Premium", onclick: () => act("Offrir 30 jours de Premium ?", u.display_name, () => api("POST", `/admin/users/${u.id}/premium`, { days: 30, note: "console" })) }),
      u.premium_until ? h("button", { class: "btn sm ghost", type: "button", text: "Retirer Premium", onclick: () => act("Retirer le Premium ?", u.display_name, () => api("POST", `/admin/users/${u.id}/premium/revoke`, { note: "console" }), true) }) : null,
      h("button", { class: "btn sm ghost", type: "button", text: u.role === "admin" ? "Retirer admin" : "Nommer admin", onclick: () => act(u.role === "admin" ? "Retirer l'accès à la console ?" : "Nommer administrateur ?", `${u.display_name} (${u.phone || u.email || "Google"})`, () => api("POST", `/admin/users/${u.id}/role`, { role: u.role === "admin" ? "user" : "admin" }), u.role !== "admin") }),
      h("button", { class: "btn sm ghost", type: "button", text: "Numéro", onclick: () => changePhone(u) }),
      h("button", { class: "btn sm ghost", type: "button", text: "Mot de passe", onclick: () => resetPassword(u) }),
      h("button", { class: "btn sm danger", type: "button", text: u.is_active ? "Désactiver" : "Réactiver", onclick: () => act(u.is_active ? "Désactiver ce compte ?" : "Réactiver ce compte ?", u.display_name, () => api("POST", `/admin/users/${u.id}/active`, { active: !u.is_active }), u.is_active) })))));
  view(form, card(null, h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", { text: "Compte" }), h("th", { class: "hide-sm", text: "Formule" }), h("th", { class: "hide-sm", text: "État" }), h("th"))),
    h("tbody", {}, ...(rows.length ? rows : [h("tr", {}, h("td", { colspan: "4", class: "empty", text: "Aucun compte." }))]))))));
}

// --- Paiements -----------------------------------------------------------------------

async function paymentsPage() {
  setPage("paiements", "Paiements");
  const list = await api("GET", CONSOLE + "/payments");
  const kind = { success: "ok", accepted: "ok", pending: "warn", failed: "bad", refused: "bad", cancelled: "mute" };
  const rows = list.map((p) => h("tr", {},
    h("td", {}, h("div", { style: "font-weight:600", text: p.user || "compte supprimé" }), h("div", { class: "note mono", text: p.phone || "" })),
    h("td", { text: number(p.amount) + " " + (p.currency === "XOF" ? "F CFA" : p.currency) }),
    h("td", { class: "hide-sm", text: p.days + " j · " + (p.method || p.provider) }),
    h("td", {}, pill(p.status, kind[p.status] || "")), h("td", { class: "hide-sm", text: when(p.created_at) })));
  view(card(null, list.length ? h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", { text: "Compte" }), h("th", { text: "Montant" }), h("th", { class: "hide-sm", text: "Formule" }), h("th", { text: "État" }), h("th", { class: "hide-sm", text: "Date" }))),
    h("tbody", {}, ...rows))) : h("div", { class: "empty", text: "Aucun paiement pour l'instant." })));
}

// --- Versions de l'application -----------------------------------------------------------

async function versionsPage() {
  setPage("versions", "Versions de l'app");
  const { current } = await api("GET", CONSOLE + "/app-release");
  const currentCard = current
    ? card(["Version proposée aux joueurs", pill("n°" + current.build, "ok")],
      h("div", { class: "row" }, h("span", { class: "t", text: "Publiée" }), h("b", { text: when(current.published_at) })),
      h("div", { class: "row" }, h("span", { class: "t", text: "Taille" }), h("b", { text: bytes(current.size) })),
      h("div", { class: "row" }, h("span", { class: "t", text: "Mise à jour obligatoire sous" }), h("b", { text: current.minimum_build ? "n°" + current.minimum_build : "non" })),
      current.notes ? h("p", { class: "muted", style: "margin:12px 0 0", text: current.notes }) : null)
    : card("Version proposée aux joueurs", h("div", { class: "empty", text: "Aucune version publiée sur ce serveur." }));
  let file = null;
  const fileName = h("div", { class: "note", text: "Aucun fichier choisi" });
  const input = h("input", { type: "file", accept: ".zip,application/zip", onchange: (e) => pick(e.target.files[0]) });
  const drop = h("label", { class: "drop" }, input, icon("i-up"), h("div", { style: "font-weight:600;margin-top:6px", text: "Choisir l'archive footprono-apk.zip" }), h("div", { class: "note", text: "téléchargée dans GitHub → Actions → Application → Artifacts" }), fileName);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); });
  function pick(f) { file = f || null; fileName.textContent = file ? `${file.name} · ${bytes(file.size)}` : "Aucun fichier choisi"; }
  const notes = h("input", { class: "input", type: "text", maxlength: "500", placeholder: "Nouveautés de cette version" });
  const minimum = h("input", { class: "input", type: "number", min: "0", placeholder: "0 = mise à jour facultative", style: "max-width:220px" });
  const progress = h("div", { hidden: true }, bar(0), h("div", { class: "note", style: "margin-top:6px" }));
  const send = h("button", { class: "btn", type: "button" }, icon("i-up"), "Publier");
  send.addEventListener("click", async () => {
    if (!file) { toast("Choisis d'abord l'archive."); return; }
    if (!(await confirmBox("Publier cette version ?", "Les téléphones la proposeront à l'ouverture de l'application.", "Publier"))) return;
    send.disabled = true; progress.hidden = false;
    const params = new URLSearchParams({ notes: notes.value.trim(), minimum: String(Number(minimum.value || 0)) });
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}${CONSOLE}/app-release?${params}`);
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      progress.firstChild.firstChild.style.width = Math.round((e.loaded / e.total) * 100) + "%";
      progress.lastChild.textContent = e.loaded < e.total ? `envoi ${Math.round((e.loaded / e.total) * 100)} %` : "vérification et publication…";
    };
    xhr.onload = () => {
      let data = null; try { data = JSON.parse(xhr.responseText); } catch { /* vide */ }
      if (xhr.status === 200) { toast("Version n°" + data.current.build + " publiée."); versionsPage(); }
      else { toast((data && data.error && data.error.message) || "Erreur " + xhr.status); send.disabled = false; progress.hidden = true; }
    };
    xhr.onerror = () => { toast("Envoi interrompu : réessaie."); send.disabled = false; progress.hidden = true; };
    xhr.send(file);
  });
  view(h("div", { class: "grid-2e", style: "margin-top:0" }, currentCard,
    card("Publier une nouvelle version", drop,
      h("div", { class: "field", style: "margin-top:14px" }, h("label", { text: "Notes de version" }), notes),
      h("div", { class: "field" }, h("label", { text: "Mise à jour obligatoire sous la version n°" }), minimum),
      progress, h("div", { class: "btns", style: "margin-top:10px" }, send))));
}

// --- Sécurité : code à 6 chiffres, sessions, historique des actions -----------------------

async function securityPage() {
  setPage("securite", "Sécurité");
  const [status, journal, alertInfo] = await Promise.all([api("GET", "/admin/security"), api("GET", CONSOLE + "/audit"), api("GET", "/admin/alerts")]);
  me.totp_enabled = status.totp_enabled;
  document.getElementById("nav-security").hidden = status.totp_enabled;

  const codeCard = status.totp_enabled
    ? card(["Code de sécurité", pill("Activé", "ok")],
      h("p", { class: "note", text: "Chaque connexion à la console demande le code à 6 chiffres de ton application d'authentification, après le mot de passe." }),
      h("div", { class: "btns" }, h("button", { class: "btn ghost", type: "button", text: "Désactiver", onclick: async () => {
        const code = await promptBox("Désactiver le code de sécurité", "Entre le code actuel de ton application d'authentification.", "123456");
        if (!code) return;
        try { await api("POST", "/admin/security/totp/disable", { code }); toast("Code de sécurité désactivé."); securityPage(); } catch (err) { toast(err.message); }
      } })))
    : card(["Code de sécurité", pill("Désactivé", "bad")],
      h("p", { class: "note", text: "Sans code, un mot de passe volé suffit pour ouvrir la console. Active-le : chaque connexion demandera aussi un code à 6 chiffres, renouvelé toutes les 30 secondes sur ton téléphone." }),
      h("div", { class: "btns" }, h("button", { class: "btn", type: "button", onclick: () => enableTotp() }, icon("i-key"), "Activer")));

  const sessionsCard = card("Sessions de la console",
    h("div", { class: "row" }, h("span", { class: "t", text: "Sessions ouvertes" }), h("b", { text: String(status.sessions) })),
    h("div", { class: "row" }, h("span", { class: "t", text: "Durée d'une session" }), h("b", { text: status.session_hours + " h" })),
    h("p", { class: "note", text: "Téléphone ou ordinateur perdu : ferme toutes les sessions, puis reconnecte-toi ici." }),
    h("div", { class: "btns" }, h("button", { class: "btn ghost", type: "button", onclick: async () => {
      if (!(await confirmBox("Déconnecter toutes les sessions ?", "Toutes les sessions de la console de ce compte sont fermées, celle-ci comprise.", "Tout déconnecter", true))) return;
      try { await api("POST", CONSOLE + "/logout-all"); } catch { /* déjà fermée */ }
      logout();
    } }, icon("i-out"), "Déconnecter toutes mes sessions")));

  const rows = journal.map((a) => h("tr", {},
    h("td", { class: "hide-sm", text: when(a.at) }),
    h("td", {}, h("div", { style: "font-weight:600", text: a.summary }), h("div", { class: "note", text: a.admin + " · " + ago(a.at) })),
    h("td", { class: "hide-sm mono", text: a.action })));
  const auditCard = card("Historique des actions",
    journal.length ? h("div", { class: "scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", { class: "hide-sm", text: "Date" }), h("th", { text: "Action" }), h("th", { class: "hide-sm", text: "Type" }))),
      h("tbody", {}, ...rows))) : h("div", { class: "empty", text: "Aucune action enregistrée pour l'instant." }));
  view(h("div", { class: "grid-2e", style: "margin-top:0" }, codeCard, sessionsCard),
    h("div", { style: "margin-top:12px" }, alertsCard(alertInfo)), h("div", { style: "margin-top:12px" }, auditCard));
}

function alertsCard(info) {
  const act = async (fn, done) => { try { await fn(); if (done) toast(done); securityPage(); } catch (err) { toast(err.message); } };
  if (!info.enabled) {
    return card(["Alertes sur ton téléphone", pill("Désactivées", "mute")],
      h("p", { class: "note", text: "Reçois une notification quand un service tombe, qu'une tâche échoue, que le quota API-Football baisse ou qu'une sauvegarde manque. Par l'application gratuite ntfy, sans compte : rien ne passe par l'application des joueurs." }),
      h("ol", { class: "howto" },
        h("li", {}, "Installe ", h("b", { text: "ntfy" }), " depuis le Play Store."),
        h("li", {}, "Crée ton canal d'alertes ci-dessous, puis abonne-toi dans ntfy.")),
      h("div", { class: "btns" }, h("button", { class: "btn", type: "button", onclick: () => act(() => api("POST", "/admin/alerts/setup")) }, icon("i-warn"), "Créer mon canal d'alertes")));
  }
  return card(["Alertes sur ton téléphone", pill("Activées", "ok")],
    h("ol", { class: "howto" },
      h("li", {}, "Sur ce téléphone : ", h("a", { href: info.subscribe_url }, "s'abonner dans ntfy"), "."),
      h("li", {}, "Ou dans ntfy : ", h("b", { text: "+" }), " → nom du sujet ci-dessous (serveur ntfy.sh par défaut).")),
    h("div", { class: "secret", text: info.topic }),
    h("p", { class: "note", text: "Garde ce nom pour toi : quiconque le connaît peut lire les alertes (aucune donnée de joueur n'y figure). Vérifications toutes les 10 minutes ; une même alerte au plus toutes les 12 h." }),
    h("div", { class: "btns" },
      h("button", { class: "btn", type: "button", onclick: () => act(() => api("POST", "/admin/alerts/test"), "Alerte d'essai envoyée : regarde ton téléphone.") }, "Envoyer une alerte d'essai"),
      h("button", { class: "btn ghost", type: "button", onclick: async () => {
        if (await confirmBox("Changer de canal ?", "L'ancien canal ne recevra plus rien : il faudra t'abonner au nouveau dans ntfy.", "Changer")) act(() => api("POST", "/admin/alerts/setup"));
      } }, "Changer de canal"),
      h("button", { class: "btn ghost", type: "button", onclick: async () => {
        if (await confirmBox("Désactiver les alertes ?", "Plus aucune alerte ne sera envoyée.", "Désactiver", true)) act(() => api("DELETE", "/admin/alerts"), "Alertes désactivées.");
      } }, "Désactiver")));
}

async function enableTotp() {
  let setup;
  try { setup = await api("POST", "/admin/security/totp/setup"); } catch (err) { toast(err.message); return; }
  const done = await modal((close) => {
    const input = h("input", { class: "input", type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: "6", placeholder: "123456" });
    const error = h("p", { class: "error", hidden: true });
    const form = h("form", { onsubmit: async (e) => {
      e.preventDefault();
      try { await api("POST", "/admin/security/totp/enable", { code: input.value.trim() }); close(true); }
      catch (err) { error.textContent = err.message; error.hidden = false; }
    } }, input, error,
      h("div", { class: "btns", style: "margin-top:12px" }, h("button", { class: "btn", type: "submit", text: "Activer" }),
        h("button", { class: "btn ghost", type: "button", text: "Annuler", onclick: () => close(false) })));
    return [h("h3", { text: "Activer le code de sécurité" }),
      h("ol", { class: "howto" },
        h("li", {}, "Installe ", h("b", { text: "Google Authenticator" }), " (ou Microsoft Authenticator) sur ton téléphone."),
        h("li", {}, "Ajoute la console : ", h("a", { href: setup.uri }, "ouvrir dans l'application"),
          " (sur ce téléphone), ou saisis cette clé à la main :")),
      h("div", { class: "secret", text: setup.secret.replace(/(.{4})/g, "$1 ").trim() }),
      h("p", { class: "note", text: "Ne partage jamais cette clé : elle n'est affichée qu'une fois et valable 10 minutes." }),
      h("ol", { class: "howto", start: "3" }, h("li", {}, "Entre le code à 6 chiffres affiché par l'application.")),
      form];
  });
  if (done) { toast("Code de sécurité activé : il sera demandé à chaque connexion."); securityPage(); }
}

// --- Plus (téléphone) -------------------------------------------------------------------

function plusPage() {
  setPage("plus", "Plus");
  view(card(null, h("div", { class: "plus-list" }, ...PAGES.filter((p) => !["dashboard", "actions", "journal"].includes(p.id)).map((p) =>
    h("a", { href: p.hash }, h("span", { class: "icon mute" }, icon(p.icon)), p.title)),
  h("a", { href: "#/", onclick: (e) => { e.preventDefault(); logout(); } }, h("span", { class: "icon bad" }, icon("i-out")), "Se déconnecter"))));
}

// --- Démarrage ---------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("login-form").addEventListener("submit", login);
  document.getElementById("login-back").addEventListener("click", () => { codeStep(false); showLogin(); });
  wireOtp();
  document.getElementById("logout").addEventListener("click", logout);
  document.getElementById("open-palette").addEventListener("click", openPalette);
  document.getElementById("fab").addEventListener("click", openPalette);
  document.getElementById("palette").addEventListener("click", (e) => { if (e.target.id === "palette") closePalette(); });
  const input = document.getElementById("palette-input");
  input.addEventListener("input", () => renderPalette(input.value));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { paletteIndex = Math.min(paletteIndex + 1, paletteItems.length - 1); drawPalette(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { paletteIndex = Math.max(paletteIndex - 1, 0); drawPalette(); e.preventDefault(); }
    else if (e.key === "Enter" && paletteItems[paletteIndex]) { const item = paletteItems[paletteIndex]; closePalette(); item.go(); }
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && me) { e.preventDefault(); openPalette(); }
    else if (e.key === "Escape") { closePalette(); }
  });
  window.addEventListener("hashchange", route);
  if (token) start(); else showLogin();
});
