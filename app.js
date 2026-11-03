// Telegram Mini App: review one conversation at a time — is the Audio pipeline text correct? is Gemma 4's?
const tg = window.Telegram && window.Telegram.WebApp;
const params = new URLSearchParams(location.search);
const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || params.get("tgWebAppStartParam") || "";
const [startSub, openId] = startParam.split("__");
const sub = startSub || params.get("api") || "";  // menu button passes the tunnel as ?api=
const API = /^[a-z0-9-]+$/.test(sub) ? `https://${sub}.trycloudflare.com` : "";
const INIT = (tg && tg.initData) || "";
const $app = document.getElementById("app");
const $toast = document.getElementById("toast");
const STEPS = [["pipeline", "Audio pipeline"], ["gemma", "Gemma 4"]];
const REASONS = ["Wrong words", "Wrong speakers", "Wrong mood", "Missing parts", "Other"];

const state = { items: [], ready: 0, teamDone: 0, myToday: 0, skipped: [], pending: [], details: new Map(), audio: new Map() };

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
const icon = (kind) => (kind === "call" ? "📞" : "🏪");
const when = (i) => `${i.date.slice(8)}/${i.date.slice(5, 7)} ${i.time}${i.duration ? " · " + i.duration : ""}`;

function toast(text, action) {
  $toast.replaceChildren(h("span", {}, text), action ? h("button", { onclick: () => { hideToast(); action.run(); } }, action.label) : null);
  $toast.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(hideToast, action ? 5000 : 2500);
}
function hideToast() { $toast.hidden = true; }

function message(title, text, button) {
  if (tg) tg.BackButton.hide();
  $app.replaceChildren(h("section", { class: "message" },
    h("h1", {}, title), h("p", {}, text), button ? h("button", { class: "capsule", onclick: button.run }, button.label) : null));
}

function showError(e, retry) {
  if (e.status === 401) return message("Session expired", "Close this window and open it again from the pinned 📝 Open review message.");
  if (e.status === 403) return message("Not allowed", "Only members of the review group can review conversations.");
  if (e.status === 0) return message("No connection", "Can't reach the review server. Check your internet and try again.", { label: "Try again", run: retry });
  message("Something went wrong", "The review server couldn't load this. Try again in a minute.", { label: "Try again", run: retry });
}

// ---------- data ----------
async function loadList() {
  const data = await (await api("/api/conversations")).json();
  state.items = data.items;
  state.ready = data.ready;
  state.teamDone = data.team_done;
  state.myToday = data.my_today;
}

const isDoneByMe = (i) => i.mine.pipeline && i.mine.gemma;
function queue() {
  const open = state.items.filter((i) => i.ready && !isDoneByMe(i));
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
      toast("Couldn't save yet — retrying…");
      await new Promise((r) => setTimeout(r, 5000));
    }
  }
  flush.busy = false;
  if (tg && tg.disableClosingConfirmation) tg.disableClosingConfirmation();
}

// ---------- review screen ----------
function progressHeader() {
  const left = queue().length;
  const total = state.items.filter((i) => i.ready).length;
  const pct = total ? Math.round(((total - left) / total) * 100) : 0;
  const fill = h("span");
  fill.style.width = `${pct}%`; // CSSOM, not a style attribute, so the CSP allows it
  return h("header", { class: "top" },
    h("div", { class: "row" },
      h("p", { class: "lead" }, left ? `${left} left for you` : "All done"),
      h("button", { class: "plain", onclick: showList }, "All conversations")),
    h("div", { class: "bar", role: "progressbar", "aria-valuenow": pct, "aria-valuemin": 0, "aria-valuemax": 100,
      "aria-label": "Your progress" }, fill),
    h("p", { class: "foot" }, `Team: ${state.teamDone} of ${state.ready} done`));
}

function player(id) {
  const audio = new Audio();
  const btn = h("button", { class: "play", disabled: true, "aria-label": "Play recording" }, "Loading recording…");
  const speed = h("button", { class: "chip", disabled: true, "aria-label": "Playback speed" }, "1×");
  const fill = h("span");
  const track = h("div", { class: "track", "aria-hidden": "true" }, fill);
  const time = h("span", { class: "foot" }, "");
  const fmt = (s) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "–:––");
  const paint = () => {
    btn.textContent = audio.paused ? "▶  Play recording" : "❚❚  Pause";
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
    .catch(() => { btn.textContent = "Recording unavailable"; });
  const box = h("section", { class: "player" }, btn, h("div", { class: "row" }, track, time, speed));
  box.stop = () => audio.pause();
  return box;
}

function transcript(result) {
  if (!result) return h("p", { class: "foot" }, "Result not ready yet.");
  if (result.error) return h("p", { class: "warn" }, "This result failed: " + result.error);
  return h("div", {},
    h("p", { class: "meta" }, h("span", { class: "pill" }, result.sentiment || "—"), result.secs ? h("span", { class: "foot" }, `took ${Math.round(result.secs)} s`) : null),
    result.summary ? h("p", { class: "summary" }, result.summary) : null,
    h("ol", { class: "turns" }, (result.turns || []).map((t) => {
      const extra = t.english && t.english !== t.text ? ` {${t.english}}` : "";
      return h("li", {}, h("b", {}, `${t.speaker || "?"}${t.sentiment ? ` (${t.sentiment})` : ""}`), ` ${t.text || ""}${extra}`);
    })));
}

function reasonSheet(onSave) {
  const picked = new Set();
  const other = h("input", { type: "text", maxlength: 200, placeholder: "Anything else? (optional)", "aria-label": "Other reason" });
  const close = () => sheet.remove();
  const sheet = h("div", { class: "sheet-bg", onclick: (e) => e.target === sheet && close() },
    h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "sheet-title" },
      h("div", { class: "grabber", "aria-hidden": "true" }),
      h("h2", { id: "sheet-title" }, "What was wrong?"),
      h("p", { class: "foot" }, "Tap all that apply."),
      h("div", { class: "chips" }, REASONS.map((r) => h("button", {
        class: "chip", "aria-pressed": "false",
        onclick: (e) => { picked.has(r) ? picked.delete(r) : picked.add(r); e.currentTarget.setAttribute("aria-pressed", String(picked.has(r))); },
      }, r))),
      other,
      h("div", { class: "row" },
        h("button", { class: "capsule ghost", onclick: close }, "Cancel"),
        h("button", { class: "capsule bad", onclick: () => { close(); onSave([...picked, other.value.trim()].filter(Boolean).join(", ")); } }, "Save as wrong"))));
  document.body.append(sheet);
  sheet.querySelector(".chip").focus();
}

async function showReview(id, startStep) {
  hideToast();
  const q = queue();
  const row = state.items.find((i) => i.id === id) || q[0];
  if (!row) return showDone();
  if (tg) tg.BackButton.hide();
  $app.replaceChildren(progressHeader(), h("div", { class: "skeleton", "aria-busy": "true", "aria-label": "Loading" }, h("span"), h("span"), h("span")));
  let d;
  try {
    d = await getDetail(row.id);
  } catch (e) {
    return showError(e, () => showReview(row.id));
  }
  prefetch(q.find((i) => i.id !== row.id)?.id);
  let step = startStep ?? (row.mine.pipeline && !row.mine.gemma ? 1 : 0);
  const audio = player(row.id);
  const body = h("section", { class: "step" });
  const done = [];
  let compare = false;

  const paint = () => {
    const [sys, label] = STEPS[step];
    const other = STEPS[1 - step];
    body.replaceChildren(
      h("p", { class: "foot" }, `Step ${step + 1} of 2`),
      h("h2", { tabindex: "-1" }, `Is the ${label} text correct?`),
      h("p", { class: "hint" }, "Listen to the recording, then check who spoke, what was said and the mood."),
      compare
        ? h("div", { class: "cols" },
            h("div", { class: "group" }, h("h3", {}, label), transcript(d[sys])),
            h("div", { class: "group" }, h("h3", {}, other[1]), transcript(d[other[0]])))
        : h("div", { class: "group" }, transcript(d[sys])),
      h("button", { class: "plain", onclick: () => { compare = !compare; paint(); } }, compare ? "Hide the other result" : `Compare with ${other[1]}`),
      h("button", { class: "plain muted", onclick: skip }, "Skip — can't hear it"));
    verdict.replaceChildren(
      h("button", { class: "capsule bad", onclick: () => reasonSheet((note) => vote("bad", note)) }, "👎  Wrong"),
      h("button", { class: "capsule ok", onclick: () => vote("ok", "") }, "👍  Correct"));
    body.querySelector("h2").focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  };

  const vote = (verdictValue, note) => {
    const sys = STEPS[step][0];
    saveVote(row.id, sys, verdictValue, note);
    done.push(sys);
    haptic(verdictValue === "ok" ? "success" : "warning");
    if (step === 0 && !row.mine.gemma) { step = 1; return paint(); }
    audio.stop();
    state.myToday += 1;
    const next = queue()[0];
    toast("Saved ✓", { label: "Undo", run: () => { done.forEach((s) => saveVote(row.id, s, "clear")); showReview(row.id, 0); } });
    next ? showReview(next.id) : showDone();
  };

  const skip = () => {
    audio.stop();
    state.skipped = [...state.skipped.filter((x) => x !== row.id), row.id];
    try { sessionStorage.setItem("skipped", JSON.stringify(state.skipped)); } catch {}
    const next = queue().find((i) => i.id !== row.id);
    next ? showReview(next.id) : showDone();
  };

  const verdict = h("div", { class: "verdict" });
  $app.replaceChildren(progressHeader(),
    h("section", { class: "who" }, h("h1", {}, `${icon(row.kind)} ${row.who}`), h("p", { class: "foot" }, `${row.store} · ${when(row)}`)),
    audio, body, verdict);
  paint();
}

function showDone() {
  if (tg) tg.BackButton.hide();
  const waiting = state.items.filter((i) => !i.ready).length;
  $app.replaceChildren(progressHeader(), h("section", { class: "message" },
    h("h1", {}, "All done 🎉"),
    h("p", {}, `You reviewed ${state.myToday} conversation${state.myToday === 1 ? "" : "s"} today.`),
    waiting ? h("p", { class: "foot" }, `${waiting} more will appear here once Gemma 4 has processed them.`) : null,
    h("button", { class: "capsule", onclick: start }, "Check for new ones"),
    h("button", { class: "plain", onclick: showList }, "See all conversations")));
}

// ---------- list (for managers / changing a vote) ----------
function showList() {
  hideToast();
  if (tg) tg.BackButton.show();
  const mark = (v) => (v === "ok" ? "👍" : v === "bad" ? "👎" : "—");
  $app.replaceChildren(
    h("header", { class: "top" }, h("h1", {}, "All conversations"), h("p", { class: "foot" }, `Team: ${state.teamDone} of ${state.ready} done · you: 👍/👎 per result`)),
    h("ul", { class: "list group" }, state.items.map((i) => h("li", {},
      h("button", { onclick: () => (i.ready ? showReview(i.id, 0) : toast("Gemma 4 hasn't processed this one yet")) },
        h("span", { class: "who-line" }, `${icon(i.kind)} ${i.who}`),
        h("span", { class: "foot" }, when(i)),
        h("span", { class: "marks" }, i.ready ? `Pipeline ${mark(i.mine.pipeline)} · Gemma ${mark(i.mine.gemma)}` : "Waiting for Gemma 4"))))));
}

// ---------- start ----------
async function start() {
  if (!INIT || !API) return message("Open from Telegram", "Open this page from the pinned 📝 Open review message in the Telegram group.");
  try { state.skipped = JSON.parse(sessionStorage.getItem("skipped") || "[]"); } catch {}
  $app.replaceChildren(h("div", { class: "skeleton", "aria-busy": "true", "aria-label": "Loading" }, h("span"), h("span"), h("span")));
  try {
    await loadList();
  } catch (e) {
    return showError(e, start);
  }
  const target = openId && state.items.find((i) => i.id === openId && i.ready);
  target ? showReview(target.id, 0) : showReview(queue()[0]?.id);
}

if (tg) {
  tg.ready();
  tg.expand();
  if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
  tg.BackButton.onClick(() => showReview(queue()[0]?.id));
}
start();
