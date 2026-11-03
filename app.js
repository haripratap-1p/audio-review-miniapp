// Telegram Mini App: review store conversations. General users see our audio pipeline; the Tech team also sees Gemma and Gemini.
const tg = window.Telegram && window.Telegram.WebApp;
const params = new URLSearchParams(location.search);
const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || params.get("tgWebAppStartParam") || "";
const [startSub, openId] = startParam.split("__");
const sub = startSub || params.get("api") || "";  // menu button passes the tunnel as ?api=
const API = /^[a-z0-9-]+$/.test(sub) ? `https://${sub}.trycloudflare.com` : "";
const INIT = (tg && tg.initData) || "";
const $app = document.getElementById("app");
const $toast = document.getElementById("toast");
// which systems and names this user may see come from the server (role-based)
let SYSTEMS = ["pipeline"];
let LABEL = { pipeline: "Audio pipeline" };
const SHORT = { pipeline: "Pipeline", gemma: "Gemma", gemini: "Gemini" };
const REASONS = ["Wrong words", "Wrong speakers", "Wrong mood", "Missing parts", "Other"];
const PAPER = { light: "#F5F5F7", dark: "#0E0E10" };  // same values as --paper in style.css
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const state = {
  items: [], total: 0, ready: 0, teamPipeline: 0, myToday: 0, filter: "all", kind: "call",
  skipped: [], pending: [], details: new Map(), audio: new Map(),
};

// ---------- theme: white or dark; the reviewer's choice wins, else Telegram's ----------
function savedTheme() {
  try { return localStorage.getItem("theme"); } catch { return null; }
}
function applyTheme() {
  const pick = savedTheme();
  const dark = pick ? pick === "dark" : tg && tg.colorScheme ? tg.colorScheme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const mode = dark ? "dark" : "light";
  document.documentElement.dataset.theme = mode;
  try { tg.setHeaderColor(PAPER[mode]); tg.setBackgroundColor(PAPER[mode]); } catch {}
  document.querySelectorAll(".theme-btn").forEach(paintThemeButton);
}
function paintThemeButton(btn) {
  const dark = document.documentElement.dataset.theme === "dark";
  btn.replaceChildren(icon(dark ? "sun" : "moon"));
  btn.setAttribute("aria-label", dark ? "Switch to white theme" : "Switch to dark theme");
}
function themeButton() {
  const btn = h("button", { class: "theme-btn", onclick: () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try { localStorage.setItem("theme", next); } catch {}
    applyTheme();
  } });
  paintThemeButton(btn);
  return btn;
}
applyTheme();
if (tg) tg.onEvent("themeChanged", applyTheme);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

// ---------- helpers ----------
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
}

const ICON_PATHS = {
  play: "M8 5v14l11-7z", pause: "M7 5h4v14H7zM13 5h4v14h-4z",
  check: "M5 12.5l4.5 4.5L19 7.5", cross: "M6 6l12 12M18 6L6 18",
  sun: "M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
};
function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const path = document.createElementNS(ns, "path");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", `ic ${name === "play" || name === "pause" ? "fill" : "stroke"}`);
  path.setAttribute("d", ICON_PATHS[name]);
  svg.append(path);
  return svg;
}

class ApiError extends Error {
  constructor(status, msg) { super(msg); this.status = status; }
}

async function api(path, opts = {}) {
  let r;
  try {
    r = await fetch(API + path, { ...opts, headers: { "X-Init-Data": INIT, "Content-Type": "application/json" } });
  } catch {
    throw new ApiError(0, "offline");
  }
  if (!r.ok) throw new ApiError(r.status, (await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
  return r;
}

const haptic = (kind) => tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(kind);
const fmtDate = (d) => `${Number(d.slice(8))} ${MONTHS[Number(d.slice(5, 7)) - 1]}`;
const todayIst = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);
const dayLabel = (d) => (d === todayIst() ? "Today" : d === new Date(Date.now() + 5.5 * 3600e3 - 864e5).toISOString().slice(0, 10) ? "Yesterday" : fmtDate(d));

function toast(text, action) {
  $toast.replaceChildren(...[h("span", {}, text), action && h("button", { class: "link", onclick: () => { hideToast(); action.run(); } }, action.label)].filter(Boolean));
  $toast.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(hideToast, action ? 5000 : 2500);
}
function hideToast() { $toast.hidden = true; }

const skeleton = () => h("div", { class: "skeleton", "aria-busy": "true", "aria-label": "Loading" }, h("span"), h("span"), h("span"));

function message(title, text, button) {
  if (tg) tg.BackButton.hide();
  $app.replaceChildren(h("section", { class: "message" },
    h("h1", {}, title), h("p", {}, text), button ? h("button", { class: "btn primary", onclick: button.run }, button.label) : null));
}

function showError(e, retry) {
  if (e.status === 401) return message("Session expired", "Close this window and open it again from the pinned Review message.");
  if (e.status === 403) return message("Not allowed", "Only members of the review group can review conversations.");
  if (e.status === 0) return message("No connection", "Can't reach the review server. Check your internet and try again.", { label: "Try again", run: retry });
  message("Something went wrong", "The review server couldn't load this. Try again in a minute.", { label: "Try again", run: retry });
}

// ---------- data ----------
async function loadList() {
  const data = await (await api("/api/conversations")).json();
  state.items = data.items;
  state.role = data.role || "general";
  state.isOwner = !!data.is_owner;
  LABEL = data.labels || { pipeline: "Audio pipeline" };
  SYSTEMS = Object.keys(LABEL);
  // in-store clips have no caller: number them per day, first clip of the day = Conversation 1 (list stays newest first)
  const perDay = new Map();
  for (const i of [...state.items].reverse().filter((x) => x.kind === "in-store")) {
    perDay.set(i.date, (perDay.get(i.date) || 0) + 1);
    i.who = `Conversation ${perDay.get(i.date)}`;
  }
  state.total = data.total ?? data.items.length;
  state.ready = data.ready;
  state.teamPipeline = data.team_pipeline ?? 0;
  state.myToday = data.my_today;
}

// a conversation is still open for me until every available result has my verdict
const has = (i, s) => (i.avail ? i.avail[s] : s === "pipeline" || (s === "gemma" && i.ready));
const isDone = (i) => SYSTEMS.every((s) => !has(i, s) || i.mine[s]);
const nextOpen = (i, after) => SYSTEMS.find((s) => s !== after && has(i, s) && !i.mine[s]);
function queue() {
  const open = state.items.filter((i) => i.kind === state.kind && !isDone(i));
  return [...open.filter((i) => !state.skipped.includes(i.id)), ...open.filter((i) => state.skipped.includes(i.id))];
}

function getDetail(id) {
  if (!state.details.has(id)) {
    state.details.set(id, api(`/api/conversation/${id}`).then((r) => r.json()).catch((e) => { state.details.delete(id); throw e; }));
  }
  return state.details.get(id);
}

function getAudio(id) {
  if (!state.audio.has(id)) {
    state.audio.set(id, api(`/api/audio/${id}`).then((r) => r.blob()).then((b) => URL.createObjectURL(b))
      .catch((e) => { state.audio.delete(id); throw e; }));
  }
  return state.audio.get(id);
}

function prefetch(id) {
  if (!id) return;
  getDetail(id).catch(() => {});
  getAudio(id).catch(() => {});
}

// votes are saved in the background; failures are retried so the reviewer never waits
function saveVote(id, system, verdict, note = "") {
  const row = state.items.find((i) => i.id === id);
  if (row) row.mine[system] = verdict === "clear" ? null : verdict;
  state.pending.push({ id, system, verdict, note });
  if (tg && tg.enableClosingConfirmation) tg.enableClosingConfirmation();
  flush();
}

async function flush() {
  if (flush.busy) return;
  flush.busy = true;
  while (state.pending.length) {
    const v = state.pending[0];
    try {
      await api("/api/review", { method: "POST", body: JSON.stringify(v) });
      state.pending.shift();
      state.details.delete(v.id);
    } catch (e) {
      if (e.status === 401 || e.status === 403) { state.pending = []; flush.busy = false; return showError(e); }
      toast("Couldn't save yet, retrying…");
      await new Promise((r) => setTimeout(r, 5000));
    }
  }
  flush.busy = false;
  if (tg && tg.disableClosingConfirmation) tg.disableClosingConfirmation();
}

// ---------- shared pieces ----------
function topbar(active) {
  const mine = state.items.filter((i) => i.kind === state.kind);
  const waiting = mine.filter((i) => SYSTEMS.some((s) => !has(i, s))).length;
  const stat = (n, label) => h("span", {}, h("b", {}, n), ` ${label}`);
  const tab = (key, text, run) => h("button", { class: "seg-btn", "aria-pressed": String(active === key), onclick: run }, text);

  const page = ["benchmark", "team"].includes(active);
  return h("header", { class: "top" },
    h("div", { class: "row between" }, h("div", { class: "top-left" }, h("h1", {}, "Review"), themeButton())),
    h("div", { class: "seg nav", role: "group", "aria-label": "View" },
      tab("queue", "Queue", () => showReview(queue()[0]?.id)), tab("all", "All", showList),
      state.role === "tech" ? tab("benchmark", "Benchmark", showBenchmark) : null,
      state.isOwner ? tab("team", "Team", showTeam) : null),
    page ? null : kindTabs(active),
    page ? null : h("p", { class: "stats" }, stat(queue().length, "for you"), stat(mine.filter((i) => i.mine.pipeline).length, "checked by you"),
      SYSTEMS.length > 1 ? stat(waiting, "waiting for Gemma or Gemini") : null));
}

function kindTabs(active) {
  const openOf = (k) => state.items.filter((i) => i.kind === k && !isDone(i)).length;
  const kindTab = (k, text) => h("button", {
    class: "kind-tab", role: "tab", "aria-selected": String(state.kind === k),
    onclick: () => { state.kind = k; active === "all" ? showList() : queue().length ? showReview(queue()[0].id) : showDone(); },
  }, text, h("span", { class: "count" }, openOf(k)));
  return h("div", { class: "kind-tabs", role: "tablist", "aria-label": "Recording type" }, kindTab("call", "Calls"), kindTab("in-store", "In-store"));
}

const badge = (v, text) => h("span", { class: `badge ${v || "todo"}` }, v === "ok" ? icon("check") : v === "bad" ? icon("cross") : null, text);
const verdictText = (v) => (v === "ok" ? "Correct" : v === "bad" ? "Wrong" : "To review");

// only one recording plays at a time; any screen change stops it
function stopAudio() {
  if (player.active) player.active.pause();
}

function player(id) {
  stopAudio();
  const audio = new Audio();
  player.active = audio;
  const btn = h("button", { class: "play", disabled: true, "aria-label": "Play recording" }, icon("play"));
  const speed = h("button", { class: "chip", disabled: true, "aria-label": "Playback speed" }, "1×");
  const fill = h("span");
  const track = h("div", { class: "track", "aria-hidden": "true" }, fill);
  const time = h("span", { class: "time" }, "0:00");
  const fmt = (s) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00");
  const paint = () => {
    btn.replaceChildren(icon(audio.paused ? "play" : "pause"));
    btn.setAttribute("aria-label", audio.paused ? "Play recording" : "Pause recording");
    fill.style.width = audio.duration ? `${(audio.currentTime / audio.duration) * 100}%` : "0";
    time.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
  };
  ["play", "pause", "timeupdate", "loadedmetadata", "ended"].forEach((ev) => audio.addEventListener(ev, paint));
  btn.addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
  speed.addEventListener("click", () => {
    audio.playbackRate = audio.playbackRate === 1 ? 1.5 : 1;
    speed.textContent = `${audio.playbackRate}×`;
  });
  track.addEventListener("click", (e) => {
    const r = track.getBoundingClientRect();
    if (audio.duration) audio.currentTime = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * audio.duration;
  });
  getAudio(id).then((url) => { audio.src = url; btn.disabled = speed.disabled = false; paint(); })
    .catch(() => { time.textContent = "Recording unavailable"; });
  const box = h("section", { class: "player" }, btn, track, time, speed);
  box.stop = () => audio.pause();
  return box;
}

function transcript(result, pending) {
  if (!result) return h("p", { class: "note" }, pending);
  if (result.error) return h("p", { class: "warn" }, "This result failed: " + result.error);
  const num = (s) => (String(s || "?").match(/\d+/) || ["?"])[0];
  return h("div", {},
    h("p", { class: "summary" }, h("span", { class: "mood" }, result.sentiment || "No mood"), result.summary ? ` ${result.summary}` : ""),
    h("ol", { class: "turns" }, (result.turns || []).map((t) => h("li", {},
      h("span", { class: "spk", title: t.speaker || "" }, num(t.speaker)),
      h("div", {},
        h("p", { class: "said" }, t.text || ""),
        t.english && t.english !== t.text ? h("p", { class: "en" }, t.english) : null,
        t.sentiment ? h("p", { class: "tone" }, t.sentiment) : null)))));
}

function reasonSheet(onSave) {
  const picked = new Set();
  const other = h("input", { type: "text", maxlength: 200, placeholder: "Anything else? (optional)", "aria-label": "Other reason" });
  const close = () => sheet.remove();
  const sheet = h("div", { class: "sheet-bg", onclick: (e) => e.target === sheet && close() },
    h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "sheet-title" },
      h("h2", { id: "sheet-title" }, "What was wrong?"),
      h("p", { class: "note" }, "Tap all that apply."),
      h("div", { class: "chips" }, REASONS.map((r) => h("button", {
        class: "chip", "aria-pressed": "false",
        onclick: (e) => { picked.has(r) ? picked.delete(r) : picked.add(r); e.currentTarget.setAttribute("aria-pressed", String(picked.has(r))); },
      }, r))),
      other,
      h("div", { class: "row" },
        h("button", { class: "btn quiet", onclick: close }, "Cancel"),
        h("button", { class: "btn bad solid", onclick: () => { close(); onSave([...picked, other.value.trim()].filter(Boolean).join(", ")); } }, "Save as wrong"))));
  document.body.append(sheet);
  sheet.querySelector(".chip").focus();
}

// ---------- review screen ----------
const wide = () => matchMedia("(min-width: 1000px)").matches;

async function showReview(id, startSys) {
  if (wide()) return showDesk(id);
  stopAudio();
  hideToast();
  const q = queue();
  const row = state.items.find((i) => i.id === id) || q[0];
  if (!row) return showDone();
  state.kind = row.kind;
  state.current = row.id;
  $app.classList.remove("wide", "page");
  if (tg) tg.BackButton.hide();
  $app.replaceChildren(topbar("queue"), skeleton());
  let d;
  try {
    d = await getDetail(row.id);
  } catch (e) {
    return showError(e, () => showReview(row.id, startSys));
  }
  prefetch(q.find((i) => i.id !== row.id)?.id);
  let cur = startSys || nextOpen(row) || "pipeline";
  const audio = player(row.id);
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const panel = h("section", { class: "panel", role: "tabpanel" });
  const verdict = h("div", { class: "verdict" });
  const done = [];

  const paint = () => {
    const notReady = !has(row, cur);
    tabs.replaceChildren(...SYSTEMS.map((s) => h("button", {
      class: "tab", role: "tab", "aria-selected": String(s === cur), onclick: () => { cur = s; paint(); },
    }, LABEL[s], row.mine[s] ? badge(row.mine[s], verdictText(row.mine[s])) : null)));
    panel.replaceChildren(transcript(d[cur], `${LABEL[cur]} isn't ready for this conversation yet. It will come back to your queue when it is.`));
    verdict.replaceChildren(
      h("div", { class: "row between" },
        h("p", { class: "ask" }, notReady ? "Nothing to check yet" : `Is the ${LABEL[cur]} result correct?`),
        h("button", { class: "link", onclick: skip }, "Skip")),
      notReady ? null : h("div", { class: "row" },
        h("button", { class: "btn bad", onclick: () => reasonSheet((note) => vote("bad", note)) }, icon("cross"), "Wrong"),
        h("button", { class: "btn ok solid", onclick: () => vote("ok", "") }, icon("check"), "Correct")));
    window.scrollTo({ top: 0, behavior: "instant" });
  };

  const vote = (v, note) => {
    const had = row.mine[cur];
    saveVote(row.id, cur, v, note);
    if (!had) done.push(cur);
    haptic(v === "ok" ? "success" : "warning");
    const nextSys = nextOpen(row, cur);
    if (nextSys) { cur = nextSys; return paint(); }
    audio.stop();
    if (done.length) state.myToday += 1;
    const next = queue()[0];
    if (done.length) toast("Saved", { label: "Undo", run: () => { done.forEach((s) => saveVote(row.id, s, "clear")); showReview(row.id, "pipeline"); } });
    next ? showReview(next.id) : showDone();
  };

  const skip = () => {
    audio.stop();
    state.skipped = [...state.skipped.filter((x) => x !== row.id), row.id];
    try { sessionStorage.setItem("skipped", JSON.stringify(state.skipped)); } catch {}
    const next = queue().find((i) => i.id !== row.id);
    next ? showReview(next.id) : showDone();
  };

  $app.replaceChildren(topbar("queue"),
    h("section", { class: "who" },
      h("div", { class: "row between" }, h("h2", {}, row.who), h("span", { class: "kind" }, row.kind === "call" ? "Call" : "In-store")),
      h("p", { class: "meta" }, h("span", {}, row.store), h("span", {}, `${fmtDate(row.date)}, ${row.time}`), row.duration ? h("span", {}, row.duration) : null)),
    audio, tabs, panel, verdict);
  paint();
}

function showDone() {
  if (wide()) return showDesk();
  stopAudio();
  if (tg) tg.BackButton.hide();
  $app.replaceChildren(topbar("queue"), h("section", { class: "message" },
    h("h1", {}, "You're up to date"),
    h("p", {}, state.myToday ? `You've checked ${state.myToday} conversation${state.myToday === 1 ? "" : "s"} today.` : "Nothing is waiting for you right now."),
    h("p", { class: "note" }, "New conversations appear here as they're processed."),
    h("button", { class: "btn primary", onclick: start }, "Refresh"),
    h("button", { class: "link", onclick: showList }, "See all conversations")));
}

// ---------- all conversations ----------
function showList() {
  if (wide()) return showDesk(state.current);
  $app.classList.remove("page");
  stopAudio();
  hideToast();
  if (tg) tg.BackButton.show();
  const filters = [["all", "All"], ["todo", "To review"]];
  const keep = (i) => i.kind === state.kind && (state.filter === "all" || !isDone(i));
  const days = new Map();
  for (const i of state.items.filter(keep)) days.set(i.date, [...(days.get(i.date) || []), i]);
  const rows = [...days].map(([date, list]) => h("section", { class: "day" },
    h("h2", {}, dayLabel(date)),
    h("ul", { class: "list" }, list.map((i) => h("li", {}, h("button", { onclick: () => showReview(i.id) },
      h("span", { class: "who-line" }, i.who),
      h("span", { class: "note" }, `${i.time}${i.duration ? `, ${i.duration}` : ""}`),
      h("span", { class: "marks" },
        SYSTEMS.map((s) => h("span", {}, `${SHORT[s]} `, has(i, s) ? badge(i.mine[s], verdictText(i.mine[s])) : h("span", { class: "badge todo" }, "Pending"))))))))));
  $app.replaceChildren(topbar("all"),
    h("div", { class: "chips filters", role: "group", "aria-label": "Filter" },
      filters.map(([k, text]) => h("button", { class: "chip", "aria-pressed": String(state.filter === k), onclick: () => { state.filter = k; showList(); } }, text))),
    ...(rows.length ? rows : [h("p", { class: "note pad" }, "No conversations match this filter.")]));
}

// ---------- PC / laptop: list on the left, both results side by side ----------
function sidebarList(selectedId) {
  const filters = [["all", "All"], ["todo", "To review"]];
  const keep = (i) => i.kind === state.kind && (state.filter === "all" || !isDone(i));
  const days = new Map();
  for (const i of state.items.filter(keep)) days.set(i.date, [...(days.get(i.date) || []), i]);
  return h("aside", { class: "side" },
    h("div", { class: "top-left" }, h("h1", {}, "Review"), themeButton()),
    state.role === "tech" ? h("div", { class: "row side-links" },
      h("button", { class: "link", onclick: showBenchmark }, "Benchmark"),
      state.isOwner ? h("button", { class: "link", onclick: showTeam }, "Team") : null) : null,
    kindTabs("queue"),
    h("div", { class: "chips filters", role: "group", "aria-label": "Filter" },
      filters.map(([k, text]) => h("button", { class: "chip", "aria-pressed": String(state.filter === k), onclick: () => { state.filter = k; showDesk(selectedId); } }, text))),
    days.size ? [...days].map(([date, list]) => h("section", { class: "day" },
      h("h2", {}, dayLabel(date)),
      h("ul", { class: "list" }, list.map((i) => h("li", {}, h("button", { "aria-current": String(i.id === selectedId), onclick: () => showDesk(i.id) },
        h("span", { class: "who-line" }, i.who),
        h("span", { class: "note" }, `${i.time}${i.duration ? `, ${i.duration}` : ""}`),
        h("span", { class: "marks" },
          SYSTEMS.map((s) => has(i, s) ? badge(i.mine[s], `${SHORT[s]} ${verdictText(i.mine[s]).toLowerCase()}`) : h("span", { class: "badge todo" }, `${SHORT[s]} pending`)))))))))
      : h("p", { class: "note pad" }, "Nothing here for this filter."));
}

async function showDesk(id) {
  $app.classList.remove("page");
  stopAudio();
  hideToast();
  if (tg) tg.BackButton.hide();
  $app.classList.add("wide");
  const row = state.items.find((i) => i.id === id) || queue()[0] || state.items.find((i) => i.kind === state.kind);
  if (row) state.kind = row.kind;
  state.current = row?.id;
  const main = h("div", { class: "desk-main" });
  $app.replaceChildren(h("div", { class: "desk" }, sidebarList(row?.id), main));
  if (!row) return main.replaceChildren(h("section", { class: "message" }, h("h1", {}, "You're up to date"),
    h("p", { class: "note" }, "New conversations appear here as they're processed."), h("button", { class: "btn primary", onclick: start }, "Refresh")));
  main.replaceChildren(skeleton());
  let d;
  try {
    d = await getDetail(row.id);
  } catch (e) {
    return showError(e, () => showDesk(row.id));
  }
  if (state.current !== row.id) return;  // user clicked another row meanwhile
  prefetch(queue().find((i) => i.id !== row.id)?.id);
  const audio = player(row.id);
  const done = [];
  const column = (sys) => {
    const pending = !has(row, sys);
    return h("section", { class: "col" },
      h("div", { class: "row between col-head" }, h("h2", {}, LABEL[sys]), row.mine[sys] ? badge(row.mine[sys], verdictText(row.mine[sys])) : null),
      h("div", { class: "col-body" }, transcript(d[sys], `${LABEL[sys]} isn't ready for this conversation yet.`)),
      pending ? null : h("div", { class: "row col-verdict" },
        h("button", { class: "btn bad", onclick: () => reasonSheet((note) => vote(sys, "bad", note)) }, icon("cross"), "Wrong"),
        h("button", { class: "btn ok solid", onclick: () => vote(sys, "ok", "") }, icon("check"), "Correct")));
  };
  const cols = h("div", { class: "cols" });
  const paint = () => cols.replaceChildren(...SYSTEMS.map(column));
  const vote = (sys, v, note) => {
    if (!row.mine[sys]) done.push(sys);
    saveVote(row.id, sys, v, note);
    haptic(v === "ok" ? "success" : "warning");
    if (!isDone(row)) return paint();
    audio.stop();
    if (done.length) state.myToday += 1;
    toast("Saved", { label: "Undo", run: () => { done.forEach((s) => saveVote(row.id, s, "clear")); showDesk(row.id); } });
    showDesk(queue()[0]?.id || row.id);
  };
  paint();
  main.replaceChildren(
    h("section", { class: "who" },
      h("div", { class: "row between" }, h("h2", {}, row.who), h("span", { class: "kind" }, row.kind === "call" ? "Call" : "In-store")),
      h("p", { class: "meta" }, h("span", {}, row.store), h("span", {}, `${fmtDate(row.date)}, ${row.time}`), row.duration ? h("span", {}, row.duration) : null)),
    audio, cols);
}

// ---------- Tech team: benchmark ----------
function pctText(sc) { return sc && sc.pct != null ? `${sc.pct}%` : "–"; }

function trendChart(days, systems) {
  // inline SVG (CSP-safe): one line per system, % correct per conversation day
  const ns = "http://www.w3.org/2000/svg";
  const W = 640, H = 200, P = 28;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "trend");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Percent correct per day for each system");
  const x = (k) => P + (days.length < 2 ? (W - 2 * P) / 2 : (k * (W - 2 * P)) / (days.length - 1));
  const y = (v) => H - P - (v / 100) * (H - 2 * P);
  for (const v of [0, 50, 100]) {
    const l = document.createElementNS(ns, "line");
    [["x1", P], ["x2", W - P], ["y1", y(v)], ["y2", y(v)], ["class", "grid"]].forEach(([k, val]) => l.setAttribute(k, val));
    const t = document.createElementNS(ns, "text");
    [["x", 2], ["y", y(v) + 4], ["class", "axis"]].forEach(([k, val]) => t.setAttribute(k, val));
    t.textContent = `${v}%`;
    svg.append(l, t);
  }
  systems.forEach((s, n) => {
    const pts = days.map((d, k) => (d[s] == null ? null : [x(k), y(d[s])])).filter(Boolean);
    if (pts.length > 1) {
      const pl = document.createElementNS(ns, "polyline");
      pl.setAttribute("points", pts.map((p) => p.join(",")).join(" "));
      pl.setAttribute("class", `series s${n}`);
      svg.append(pl);
    }
    pts.forEach(([cx, cy]) => {
      const c = document.createElementNS(ns, "circle");
      [["cx", cx], ["cy", cy], ["r", 3.5], ["class", `dot s${n}`]].forEach(([k, val]) => c.setAttribute(k, val));
      svg.append(c);
    });
  });
  if (days.length) {
    [[0, "start"], [days.length - 1, "end"]].forEach(([k, anchor]) => {
      const t = document.createElementNS(ns, "text");
      [["x", x(k)], ["y", H - 6], ["class", "axis"], ["text-anchor", anchor]].forEach(([a, val]) => t.setAttribute(a, val));
      t.textContent = fmtDate(days[k].date);
      svg.append(t);
    });
  }
  return svg;
}

async function showBenchmark() {
  stopAudio();
  hideToast();
  if (tg) tg.BackButton.show();
  $app.classList.remove("wide");
  $app.classList.add("page");
  $app.replaceChildren(topbar("benchmark"), skeleton());
  let b;
  try {
    b = await (await api("/api/benchmark")).json();
  } catch (e) {
    return showError(e, showBenchmark);
  }
  const sys = Object.keys(b.systems);
  const card = (s, n) => h("section", { class: `score s${n}` },
    h("h2", {}, b.labels[s]),
    h("p", { class: "big" }, pctText(b.systems[s].all)),
    h("p", { class: "note" }, `correct, ${b.systems[s].all.checked} checked of ${b.systems[s].all.available}`));
  const cell = (sc) => h("td", {}, pctText(sc), h("span", { class: "note" }, ` (${sc.checked})`));
  $app.replaceChildren(topbar("benchmark"),
    h("div", { class: "scores" }, sys.map(card)),
    h("section", { class: "panel-block" }, h("h2", {}, "Calls and in-store"),
      h("table", { class: "grid-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "System"), h("th", {}, "All"), h("th", {}, "Calls"), h("th", {}, "In-store"))),
        h("tbody", {}, sys.map((s) => h("tr", {}, h("th", {}, b.labels[s]),
          cell(b.systems[s].all), cell(b.systems[s].call), cell(b.systems[s]["in-store"])))))),
    h("section", { class: "panel-block" }, h("h2", {}, "Trend by day"),
      h("div", { class: "legend" }, sys.map((s, n) => h("span", { class: `key s${n}` }, b.labels[s]))),
      b.days.length ? trendChart(b.days, sys) : h("p", { class: "note" }, "No reviewed days yet.")),
    h("section", { class: "panel-block" }, h("h2", {}, "Reviewers"),
      b.reviewers.length ? h("table", { class: "grid-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Name"), h("th", {}, "Today"), h("th", {}, "Total"))),
        h("tbody", {}, b.reviewers.map((p) => h("tr", {}, h("th", {}, p.name), h("td", {}, p.today), h("td", {}, p.total)))))
        : h("p", { class: "note" }, "No reviews yet.")));
}

// ---------- owner: who is in the Tech team ----------
async function showTeam() {
  stopAudio();
  hideToast();
  if (tg) tg.BackButton.show();
  $app.classList.remove("wide");
  $app.classList.add("page");
  $app.replaceChildren(topbar("team"), skeleton());
  let people;
  try {
    people = (await (await api("/api/team")).json()).people;
  } catch (e) {
    return showError(e, showTeam);
  }
  const render = () => $app.replaceChildren(topbar("team"),
    h("p", { class: "note pad" }, "Tech team members see Gemma and Gemini results and the benchmark. Everyone else sees only the audio pipeline."),
    h("ul", { class: "list" }, people.map((p) => h("li", { class: "person" },
      h("div", {}, h("span", { class: "who-line" }, p.name), h("span", { class: "note" }, `${p.username ? "@" + p.username + ", " : ""}last opened ${fmtDate(p.last_seen.slice(0, 10))} ${p.last_seen.slice(11, 16)}`)),
      p.owner ? h("span", { class: "badge todo" }, "Owner") : h("button", {
        class: "switch", role: "switch", "aria-checked": String(p.tech), "aria-label": `Tech team: ${p.name}`,
        onclick: async () => {
          try {
            people = (await (await api("/api/team", { method: "POST", body: JSON.stringify({ id: p.id, tech: !p.tech }) })).json()).people;
            render();
            toast("Saved");
          } catch (e) {
            showError(e, showTeam);
          }
        },
      }, h("span", { class: "knob" }), p.tech ? "Tech team" : "General")))));
  render();
}

// switching between phone and PC widths re-renders the current view
matchMedia("(min-width: 1000px)").addEventListener("change", (e) => {
  if (!state.items.length) return;
  if (!e.matches) { $app.classList.remove("wide"); return state.current ? showReview(state.current) : showDone(); }
  showDesk(state.current);
});

// ---------- start ----------
async function start() {
  if (!INIT || !API) return message("Open from Telegram", "Open this page from the pinned Review message in the Telegram group.");
  try { state.skipped = JSON.parse(sessionStorage.getItem("skipped") || "[]"); } catch {}
  $app.replaceChildren(skeleton());
  try {
    await loadList();
  } catch (e) {
    return showError(e, start);
  }
  const target = openId && state.items.find((i) => i.id === openId);
  target ? showReview(target.id) : queue().length ? showReview(queue()[0].id) : showDone();
}

const DESKTOP = ["tdesktop", "macos", "web", "weba", "webk", "unigram"];
if (tg) {
  tg.ready();
  tg.expand();
  // laptops / PCs: open full screen so the list + A/B/C columns fit; phones keep the normal sheet
  if (DESKTOP.includes(tg.platform) && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0") && tg.requestFullscreen) {
    try { tg.requestFullscreen(); } catch {}
  }
  if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
  tg.BackButton.onClick(() => (queue().length ? showReview(queue()[0].id) : showDone()));
}
start();
