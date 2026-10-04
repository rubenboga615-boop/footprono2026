// Console d'administration FootProno : tableau de bord, actions, journal, exploitation.
// Le catalogue des actions vient du serveur : une action ajoutée côté serveur apparaît
// ici sans modifier ce fichier. Aucune donnée n'est insérée en HTML brut (textContent).
"use strict";

const API = "/api/v1";
const CONSOLE = "/admin/console";
const TOKEN_KEY = "fp_admin_token";
const POLL_MS = 1500;

let token = readToken();
let me = null;
let catalog = null;
let timer = null;
let prefill = null; // { action, params } pour « Relancer »

// --- Outils -----------------------------------------------------------------

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
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function api(method, path, body) {
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(API + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await response.json(); } catch { /* réponse vide */ }
  if (response.status === 401 && path !== "/auth/login") {
    logout();
    throw new ApiError("Session expirée : reconnecte-toi.", 401);
  }
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

function chip(text, kind) {
  return h("span", { class: "chip " + (kind || ""), text });
}

const fmtDateTime = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
const fmtTime = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });

function when(value) {
  if (!value) return "—";
  const d = new Date(value);
  const today = new Date();
  return d.toDateString() === today.toDateString() ? "aujourd'hui " + fmtTime.format(d) : fmtDateTime.format(d);
}

function duration(start, end) {
  if (!start) return "";
  const seconds = Math.max(0, Math.round(((end ? new Date(end) : new Date()) - new Date(start)) / 1000));
  if (seconds < 60) return seconds + " s";
  if (seconds < 3600) return Math.round(seconds / 60) + " min";
  return Math.floor(seconds / 3600) + " h " + String(Math.round((seconds % 3600) / 60)).padStart(2, "0");
}

function number(n) {
  return new Intl.NumberFormat("fr-FR").format(n);
}

function toast(message) {
  const el = h("div", { class: "toast", role: "status", text: message });
  document.body.append(el);
  setTimeout(() => el.remove(), 3500);
}

const STATUS = {
  queued: ["En attente", "inf"],
  running: ["En cours", "acc"],
  succeeded: ["Terminée", "ok"],
  failed: ["Échec", "bad"],
  cancelled: ["Arrêtée", "warn"],
};
const RUN_STATUS = { ok: "ok", partial: "warn", error: "bad", failed: "bad", running: "acc", interrupted: "bad" };
const RISK = {
  lecture: ["Lecture seule", "ok"],
  modifie: ["Modifie les données", "inf"],
  irreversible: ["Irréversible", "bad"],
};

function statusChip(status) {
  const [label, kind] = STATUS[status] || [status, ""];
  return chip(label, kind);
}

function card(title, ...children) {
  return h("section", { class: "card" }, title ? h("h2", {}, ...[].concat(title)) : null, ...children);
}

function stat(label, value, sub, fraction) {
  const bar = fraction === undefined ? null : h("div", { class: "bar" }, h("i"));
  if (bar) bar.firstChild.style.width = Math.round(Math.min(1, Math.max(0, fraction)) * 100) + "%";
  return h("div", { class: "card" }, h("div", { class: "k", text: label }), h("div", { class: "v", text: value }),
    sub ? h("div", { class: "s", text: sub }) : null, bar);
}

function row(left, middle, right, onclick) {
  return h("div", { class: "row" + (onclick ? " link" : ""), onclick },
    h("span", {}, left), middle ? h("span", { class: "t" }, middle) : null, right || null);
}

async function getCatalog() {
  if (!catalog) catalog = await api("GET", CONSOLE + "/actions");
  return catalog;
}

// --- Connexion ----------------------------------------------------------------

function showLogin(message) {
  document.getElementById("shell").hidden = true;
  document.getElementById("login").hidden = false;
  const error = document.getElementById("login-error");
  error.hidden = !message;
  error.textContent = message || "";
}

function logout() {
  token = null;
  me = null;
  catalog = null;
  writeToken(null);
  stopTimer();
  showLogin();
}

async function login(event) {
  event.preventDefault();
  const form = event.target;
  const button = form.querySelector("button");
  const phone = form.phone.value.trim();
  if (!phone.startsWith("+") && !phone.startsWith("00")) {
    showLogin("Numéro sans indicatif : écris-le avec l'indicatif du pays, ex. +225 " + phone);
    return;
  }
  button.disabled = true;
  try {
    const data = await api("POST", "/auth/login", {
      phone,
      password: form.password.value,
    });
    token = data.access_token;
    await start();
    if (me) {
      writeToken(token);
      form.password.value = "";
    }
  } catch (err) {
    showLogin(err.message);
  } finally {
    button.disabled = false;
  }
}

async function start() {
  try {
    me = await api("GET", "/me");
  } catch (err) {
    token = null;
    showLogin(err.status === 401 ? null : err.message);
    return;
  }
  if (me.role !== "admin") {
    token = null;
    me = null;
    writeToken(null);
    showLogin("Ce compte n'est pas administrateur.");
    return;
  }
  document.getElementById("login").hidden = true;
  document.getElementById("shell").hidden = false;
  document.getElementById("who").textContent = me.display_name + " · " + me.phone;
  route();
}

// --- Navigation -----------------------------------------------------------------

function stopTimer() {
  if (timer) clearTimeout(timer);
  timer = null;
}

function setPage(page, title) {
  document.getElementById("title").textContent = title;
  document.title = "FootProno · " + title;
  for (const a of document.querySelectorAll(".nav a")) a.classList.toggle("on", a.dataset.page === page);
  document.getElementById("side").classList.remove("open");
}

function setStatus(text, kind) {
  const el = document.getElementById("status");
  el.className = "chip " + (kind || "");
  el.textContent = text || "";
  el.hidden = !text;
}

function view(...children) {
  const el = document.getElementById("view");
  el.replaceChildren(...children);
  return el;
}

async function route() {
  stopTimer();
  setStatus("");
  if (!me) return;
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  try {
    if (parts[0] === "actions" && parts[1]) await actionForm(parts[1]);
    else if (parts[0] === "actions") await actionsPage();
    else if (parts[0] === "journal") await journalPage();
    else if (parts[0] === "jobs" && parts[1]) await jobPage(Number(parts[1]));
    else if (parts[0] === "codes") await codesPage();
    else if (parts[0] === "comptes") await accountsPage();
    else await dashboardPage();
  } catch (err) {
    if (err.status !== 401) view(card("Erreur", h("p", { class: "error", text: err.message })));
  }
}

// --- Tableau de bord ---------------------------------------------------------------

async function dashboardPage() {
  setPage("dashboard", "Tableau de bord");
  const d = await api("GET", CONSOLE + "/dashboard");
  const s = d.services;
  const allOk = s.database && s.redis && s.workers > 0;
  setStatus(allOk ? "● Tous les services répondent" : "● Un service ne répond pas", allOk ? "ok" : "bad");

  const services = [s.redis ? "Redis ✓" : "Redis ✗", s.workers > 0 ? `worker ✓ (${s.workers})` : "worker ✗"].join(" · ");
  const disk = d.disk
    ? stat("Disque", d.disk.free_gb + " Go libres", "sur " + d.disk.total_gb + " Go", 1 - d.disk.free_gb / d.disk.total_gb)
    : stat("Disque", "—", "inconnu");

  const runRow = (label, run) => run
    ? row(label, when(run.started_at) + (run.finished_at ? " · " + duration(run.started_at, run.finished_at) : ""),
      chip(run.status, RUN_STATUS[run.status]))
    : row(label, "jamais", chip("—"));
  const quality = d.quality
    ? row("Qualité (dernière ingestion)", `${d.quality.errors} erreur(s), ${d.quality.warnings} avert.`,
      chip(d.quality.status, d.quality.errors ? "bad" : d.quality.warnings ? "warn" : "ok"))
    : null;
  const coupons = row("Coupons du jour", d.coupons_today.count + " créé(s)",
    d.coupons_today.missing_codes.length ? chip("codes à saisir", "warn") : chip(d.coupons_today.count ? "OK" : "—", d.coupons_today.count ? "ok" : ""),
    () => { location.hash = "#/codes"; });

  const todo = d.todo.length
    ? d.todo.map((t) => {
      const kind = { error: "bad", warning: "warn", info: "inf" }[t.level];
      let go = null;
      if (t.action) go = h("button", { class: "btn small ghost", text: "Lancer", onclick: () => { location.hash = "#/actions/" + t.action; } });
      if (t.link === "codes") go = h("button", { class: "btn small ghost", text: "Saisir", onclick: () => { location.hash = "#/codes"; } });
      return h("div", { class: "row" }, h("span", {}, chip("●", kind), " ", t.text), go);
    })
    : [h("div", { class: "empty", text: "Rien à traiter." })];

  const jobs = d.jobs.length
    ? d.jobs.map((j) => row(j.title, when(j.created_at), statusChip(j.status), () => { location.hash = "#/jobs/" + j.id; }))
    : [h("div", { class: "empty", text: "Aucune action lancée depuis la console." })];

  view(
    h("div", { class: "grid4" },
      stat("Services", allOk ? "En marche" : "À vérifier", services),
      disk,
      stat("Comptes", number(d.users.total), "dont " + number(d.users.premium) + " Premium"),
      stat("Version du serveur", d.version, d.environment)),
    h("div", { class: "grid2" },
      card(["Tâches automatiques", chip("dernières exécutions", "acc")],
        runRow("Ingestion (06:15)", d.last.ingestion),
        runRow("Pronostics (07:45, 16:45)", d.last.prediction),
        row("Cotes (toutes les 3 h)", d.last.odds_at ? when(d.last.odds_at) : "jamais", null),
        quality, coupons),
      card(["À traiter", d.todo.length ? chip(String(d.todo.length), "warn") : chip("0", "ok")], ...todo)),
    h("div", { class: "grid2" },
      card(["Dernières actions", h("a", { href: "#/journal", class: "small", text: "Tout le journal" })], ...jobs),
      card("Raccourcis",
        h("div", { class: "btns" },
          ...["api_quota", "collect_odds", "quality", "coverage"].map((id) =>
            h("button", { class: "btn ghost small", text: shortcutLabel(id), onclick: () => { location.hash = "#/actions/" + id; } }))),
        h("p", { class: "small muted", text: "Mise à jour du serveur (git pull, redémarrage) et secrets : restent hors de la console, sur le serveur." }))));
  timer = setTimeout(route, 30000);
}

function shortcutLabel(id) {
  return { api_quota: "Quota API-Football", collect_odds: "Relever les cotes", quality: "Qualité", coverage: "Couverture" }[id] || id;
}

// --- Actions -----------------------------------------------------------------------

let familyFilter = "Toutes";

async function actionsPage() {
  setPage("actions", "Actions");
  const actions = await getCatalog();
  const families = ["Toutes", ...new Set(actions.map((a) => a.family))];
  const list = h("div", { class: "actions" });
  const filters = h("div", { class: "filters" });

  function render() {
    filters.replaceChildren(...families.map((f) =>
      h("button", { class: "f" + (f === familyFilter ? " on" : ""), type: "button", text: f, onclick: () => { familyFilter = f; render(); } })));
    list.replaceChildren(...actions.filter((a) => familyFilter === "Toutes" || a.family === familyFilter).map(actionCard));
  }
  render();
  view(h("p", { class: "muted small", text: "Le catalogue est fourni par le serveur : une nouvelle action apparaît ici dès la mise à jour du serveur." }), filters, list);
}

function actionMeta(a) {
  const [riskLabel, riskKind] = RISK[a.risk] || [a.risk, ""];
  return h("div", { class: "meta" },
    chip(a.family, "acc"), chip(riskLabel, riskKind),
    a.exclusive ? chip("une à la fois", "warn") : null,
    a.cost ? chip(a.cost) : null, a.duration ? chip(a.duration) : null);
}

function actionCard(a) {
  return h("div", { class: "act" },
    h("div", { class: "ttl", text: a.title }),
    h("div", { class: "d", text: a.description }),
    actionMeta(a),
    h("button", { class: "btn", type: "button", text: a.params.length ? "Configurer et lancer" : "Lancer", onclick: () => { location.hash = "#/actions/" + a.id; } }));
}

function paramField(p, initial) {
  const value = initial === undefined ? p.default : initial;
  const wrap = h("div", {});
  const label = h("span", { class: "lbl", text: p.label });
  let read;
  if (p.kind === "choices") {
    const chosen = new Set(value || []);
    const pills = h("div", { class: "pills" });
    const render = () => pills.replaceChildren(...p.options.map((o) =>
      h("button", {
        class: "p" + (chosen.has(o.value) ? " on" : ""), type: "button", text: o.label,
        onclick: () => { chosen.has(o.value) ? chosen.delete(o.value) : chosen.add(o.value); render(); },
      })));
    render();
    const all = h("button", { class: "btn ghost small", type: "button", text: "Tout", onclick: () => { p.options.forEach((o) => chosen.add(o.value)); render(); } });
    const none = h("button", { class: "btn ghost small", type: "button", text: "Aucun", onclick: () => { chosen.clear(); render(); } });
    wrap.append(label, h("div", { class: "btns" }, all, none), h("div", { class: "help", text: "" }), pills);
    read = () => p.options.map((o) => o.value).filter((v) => chosen.has(v));
  } else if (p.kind === "choice") {
    const select = h("select", { class: "input" }, ...p.options.map((o) => h("option", { value: o.value, text: o.label, selected: o.value === value })));
    wrap.append(label, select);
    read = () => select.value;
  } else if (p.kind === "int") {
    const input = h("input", { class: "input narrow", type: "number", step: "1", min: p.min, max: p.max, value: value ?? "" });
    wrap.append(label, input);
    read = () => (input.value === "" ? null : Number(input.value));
  } else if (p.kind === "bool") {
    const box = h("input", { type: "checkbox", checked: !!value });
    wrap.append(h("label", { class: "check" }, box, p.label));
    read = () => box.checked;
  } else {
    const input = h("input", { class: "input", type: "text", maxlength: "200", value: value ?? "" });
    wrap.append(label, input);
    read = () => input.value;
  }
  if (p.help) wrap.append(h("div", { class: "help", text: p.help }));
  return { el: wrap, read };
}

async function actionForm(actionId) {
  setPage("actions", "Actions");
  const actions = await getCatalog();
  const a = actions.find((x) => x.id === actionId);
  if (!a) {
    view(card("Action inconnue", h("p", { class: "muted", text: "Cette action n'existe pas (ou plus) sur ce serveur." })));
    return;
  }
  const initial = prefill && prefill.action === a.id ? prefill.params : {};
  prefill = null;
  const fields = a.params.map((p) => ({ p, ...paramField(p, initial[p.name]) }));
  const confirmBox = a.confirm ? h("input", { type: "checkbox" }) : null;
  const error = h("p", { class: "error", hidden: true });
  const launch = h("button", { class: "btn", type: "submit", text: "Lancer" });

  async function submit(event) {
    event.preventDefault();
    error.hidden = true;
    if (confirmBox && !confirmBox.checked) {
      error.textContent = "Coche la confirmation : cette action est irréversible.";
      error.hidden = false;
      return;
    }
    const params = {};
    for (const f of fields) params[f.p.name] = f.read();
    launch.disabled = true;
    try {
      const job = await api("POST", CONSOLE + "/jobs", { action: a.id, params, confirmed: !!confirmBox });
      location.hash = "#/jobs/" + job.id;
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      launch.disabled = false;
    }
  }

  view(h("div", { class: "panel" },
    card([a.title, h("a", { href: "#/actions", class: "small", text: "← Actions" })],
      h("p", { class: "muted", text: a.description }),
      actionMeta(a),
      h("form", { class: "form", onsubmit: submit },
        ...fields.map((f) => f.el),
        confirmBox ? h("label", { class: "confirm check" }, confirmBox, "Je confirme : cette action est irréversible.") : null,
        error,
        h("div", { class: "btns" }, launch)))));
}

// --- Journal -------------------------------------------------------------------------

async function journalPage() {
  setPage("journal", "Journal");
  const jobs = await api("GET", CONSOLE + "/jobs?limit=100");
  const body = jobs.length
    ? jobs.map((j) => h("tr", { class: "link", onclick: () => { location.hash = "#/jobs/" + j.id; } },
      h("td", { class: "mono", text: "n°" + j.id }),
      h("td", { text: j.title }),
      h("td", {}, statusChip(j.status)),
      h("td", { text: when(j.created_at) }),
      h("td", { text: duration(j.started_at, j.finished_at) }),
      h("td", { class: "small muted", text: j.summary || "" })))
    : [h("tr", {}, h("td", { colspan: "6", class: "empty", text: "Aucune action lancée." }))];
  view(card(null, h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, ...["", "Action", "État", "Lancée", "Durée", "Résumé"].map((t) => h("th", { text: t })))),
    h("tbody", {}, ...body)))));
  timer = setTimeout(route, 15000);
}

function lineClass(text) {
  if (/^(Erreur|erreur|échec|.*Error:)/.test(text)) return "err";
  if (/^Fin :/.test(text)) return "end";
  return null;
}

async function jobPage(jobId) {
  setPage("journal", "Tâche n°" + jobId);
  let last = 0;
  const log = h("div", { class: "log", "aria-live": "polite" });
  const head = h("div", {});
  const actions = await getCatalog();

  function renderHead(job) {
    const a = actions.find((x) => x.id === job.action);
    const active = job.status === "queued" || job.status === "running";
    const bar = h("div", { class: "bar" }, h("i"));
    bar.firstChild.style.width = Math.round((job.progress || 0) * 100) + "%";
    const params = Object.entries(job.params || {}).map(([k, v]) => {
      const p = a && a.params.find((x) => x.name === k);
      const shown = Array.isArray(v) ? (v.length > 6 ? v.length + " choisis" : v.join(", ")) : String(v === "" ? "défaut" : v);
      return (p ? p.label : k) + " : " + shown;
    });
    const buttons = [];
    if (active && (job.status === "queued" || (a && a.stoppable)) && !job.stop_requested) {
      buttons.push(h("button", { class: "btn danger", type: "button", text: "Arrêter", onclick: () => stop(job.id) }));
    }
    if (job.stop_requested && active) buttons.push(chip("arrêt demandé…", "warn"));
    if (!active && a) {
      buttons.push(h("button", { class: "btn ghost", type: "button", text: "Relancer avec les mêmes réglages", onclick: () => {
        prefill = { action: a.id, params: job.params };
        location.hash = "#/actions/" + a.id;
      } }));
    }
    const silent = job.silent_seconds && job.silent_seconds > 120
      ? h("p", { class: "small", text: "Aucun signe de vie depuis " + duration(new Date(Date.now() - job.silent_seconds * 1000)) + " (calcul long, ou serveur redémarré)." })
      : null;
    head.replaceChildren(card([job.title, statusChip(job.status)],
      h("div", { class: "s muted small", text: "Lancée " + when(job.created_at) + (job.started_at ? " · durée " + duration(job.started_at, job.finished_at) : "") }),
      params.length ? h("div", { class: "small muted", text: params.join(" · ") }) : null,
      bar,
      job.summary ? h("p", { text: job.summary }) : null,
      silent,
      buttons.length ? h("div", { class: "btns" }, ...buttons) : null));
    setStatus(STATUS[job.status] ? STATUS[job.status][0] : job.status, STATUS[job.status] ? STATUS[job.status][1] : "");
  }

  async function stop(id) {
    try {
      await api("POST", `${CONSOLE}/jobs/${id}/stop`);
      toast("Arrêt demandé.");
      poll();
    } catch (err) {
      toast(err.message);
    }
  }

  async function poll() {
    stopTimer();
    const job = await api("GET", `${CONSOLE}/jobs/${jobId}?after=${last}`);
    renderHead(job);
    if (job.lines.length) {
      const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
      for (const line of job.lines) {
        log.append(h("div", { class: lineClass(line.text), text: line.text || " " }));
        last = line.n;
      }
      if (atBottom) log.scrollTop = log.scrollHeight;
    }
    if (job.status === "queued" || job.status === "running" || job.lines.length === 1000) {
      timer = setTimeout(() => poll().catch(() => { timer = setTimeout(poll, POLL_MS * 4); }), POLL_MS);
    }
  }

  view(head, log);
  await poll();
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
  view(h("p", { class: "muted small", text: "Recrée chaque coupon chez 1xBet, puis colle ici son code de réservation : les joueurs le copient dans l'application. Quand tous les codes sont saisis, la notification « coupons du jour disponibles » part d'elle-même." }),
    h("div", { class: "grid2" }, ...data.coupons.map((c) => {
      const current = (c.booking_codes.find((b) => b.bookmaker === "1xbet") || {}).code || "";
      const input = h("input", { class: "input narrow mono", type: "text", maxlength: "32", value: current, placeholder: "code 1xBet" });
      const save = h("button", { class: "btn small", type: "button", text: "Enregistrer", onclick: async () => {
        save.disabled = true;
        try {
          await api("PUT", `/admin/smart-coupons/${c.id}/booking-code`, { bookmaker: "1xbet", code: input.value });
          toast(input.value.trim() ? "Code enregistré." : "Code retiré.");
          codesPage();
        } catch (err) {
          toast(err.message);
          save.disabled = false;
        }
      } });
      return card([c.profile_label, current ? chip("code saisi", "ok") : chip("code à saisir", "warn")],
        h("div", { class: "small muted", text: `${c.selections.length} sélections · cote ${c.total_odds} · probabilité ${Math.round(c.probability * 100)} %` }),
        h("div", {}, ...c.selections.map((s) => h("div", { class: "sel", text: selectionText(s) }))),
        h("div", { class: "btns" }, input, save));
    })));
}

// --- Comptes et Premium --------------------------------------------------------------

async function accountsPage(query) {
  setPage("comptes", "Comptes et Premium");
  const q = query === undefined ? "" : query;
  const users = await api("GET", "/admin/users?limit=100" + (q ? "&q=" + encodeURIComponent(q) : ""));
  const search = h("input", { class: "input", type: "search", placeholder: "Nom ou numéro", value: q });
  const form = h("form", { class: "btns", onsubmit: (e) => { e.preventDefault(); accountsPage(search.value.trim()); } },
    search, h("button", { class: "btn", type: "submit", text: "Chercher" }));

  async function act(label, fn) {
    if (!window.confirm(label + " ?")) return;
    try {
      await fn();
      toast("Fait.");
      accountsPage(q);
    } catch (err) {
      toast(err.message);
    }
  }

  const rows = users.map((u) => h("tr", {},
    h("td", {}, u.display_name, u.role === "admin" ? [" ", chip("admin", "acc")] : null),
    h("td", { class: "mono", text: u.phone }),
    h("td", {}, chip(u.plan, u.plan === "free" ? "" : "ok"), u.premium_until ? h("div", { class: "small muted", text: "jusqu'au " + fmtDateTime.format(new Date(u.premium_until)) }) : null),
    h("td", {}, u.is_active ? chip("actif", "ok") : chip("désactivé", "bad")),
    h("td", {}, h("div", { class: "btns" },
      h("button", { class: "btn small", type: "button", text: "+30 j Premium", onclick: () => act(`Offrir 30 jours de Premium à ${u.display_name}`, () => api("POST", `/admin/users/${u.id}/premium`, { days: 30, note: "console" })) }),
      u.premium_until ? h("button", { class: "btn small ghost", type: "button", text: "Retirer Premium", onclick: () => act(`Retirer le Premium de ${u.display_name}`, () => api("POST", `/admin/users/${u.id}/premium/revoke`, { note: "console" })) }) : null,
      h("button", { class: "btn small danger", type: "button", text: u.is_active ? "Désactiver" : "Réactiver", onclick: () => act(`${u.is_active ? "Désactiver" : "Réactiver"} le compte de ${u.display_name}`, () => api("POST", `/admin/users/${u.id}/active`, { active: !u.is_active })) })))));
  view(form, card(null, h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, ...["Nom", "Numéro", "Formule", "État", ""].map((t) => h("th", { text: t })))),
    h("tbody", {}, ...(rows.length ? rows : [h("tr", {}, h("td", { colspan: "5", class: "empty", text: "Aucun compte." }))]))))));
}

// --- Démarrage ---------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("login-form").addEventListener("submit", login);
  document.getElementById("logout").addEventListener("click", logout);
  document.getElementById("menu").addEventListener("click", () => document.getElementById("side").classList.toggle("open"));
  window.addEventListener("hashchange", route);
  if (token) start();
  else showLogin();
});
