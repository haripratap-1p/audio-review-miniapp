// Telegram Mini App: review Pipeline vs Gemma 4 per conversation (✅/❌); data comes from the review API on thor02.
const tg = window.Telegram && window.Telegram.WebApp;
const params = new URLSearchParams(location.search);
const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || params.get("tgWebAppStartParam") || "";
const [sub, openId] = startParam.split("__");
const API = sub ? `https://${sub}.trycloudflare.com` : "";
const INIT = (tg && tg.initData) || "";
const $app = document.getElementById("app");
const SYSTEMS = { pipeline: "Audio pipeline", gemma: "Gemma 4 12B" };
let items = [];
let tab = "todo";
let day = "";

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

async function api(path, opts = {}) {
  const r = await fetch(API + path, { ...opts, headers: { "X-Init-Data": INIT, "Content-Type": "application/json" } });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
  return r;
}

const say = (msg) => (tg && tg.showAlert ? tg.showAlert(msg) : alert(msg));
const icon = (v) => (v === "ok" ? "✅" : v === "bad" ? "❌" : "⏳");
const mineDone = (i) => i.votes.pipeline.mine && (!i.gemma || i.votes.gemma.mine);
const teamDone = (i) => i.gemma && i.votes.pipeline.result && i.votes.gemma.result;

function renderList() {
  if (tg) tg.BackButton.hide();
  const ready = items.filter((i) => i.gemma);
  const done = ready.filter(teamDone).length;
  const shown = items.filter((i) => (!day || i.date === day) && (tab === "all" || (tab === "done") === Boolean(mineDone(i))));
  const tabBtn = (id, label) => h("button", { class: tab === id ? "tab on" : "tab", onclick: () => { tab = id; renderList(); } }, label);
  const dates = [...new Set(items.map((i) => i.date))];
  $app.replaceChildren(
    h("header", {},
      h("h1", {}, "Pipeline vs Gemma 4"),
      h("p", { class: "muted" }, `Team reviewed ${done} of ${ready.length} · ${ready.length - done} left`)),
    h("div", { class: "bar" },
      tabBtn("todo", "To review"), tabBtn("done", "My reviews"), tabBtn("all", "All"),
      h("select", { onchange: (e) => { day = e.target.value; renderList(); } },
        h("option", { value: "" }, "All dates"),
        dates.map((d) => h("option", { value: d, selected: d === day }, d)))),
    shown.length
      ? h("ul", { class: "list" }, shown.map((i) =>
          h("li", { onclick: () => openItem(i.id) },
            h("div", { class: "who" }, `${i.kind === "call" ? "📞" : "🏪"} ${i.who}`),
            h("div", { class: "muted" }, `${i.store} · ${i.date} ${i.time}${i.duration ? " · " + i.duration : ""}`),
            h("div", { class: "chips" },
              h("span", {}, `Pipeline ${icon(i.votes.pipeline.result)}`),
              h("span", {}, i.gemma ? `Gemma ${icon(i.votes.gemma.result)}` : "Gemma pending")))))
      : h("p", { class: "empty" }, tab === "todo" ? "Nothing left to review 🎉" : "No conversations here."));
}

function turnLine(t) {
  const extra = t.english && t.english !== t.text ? ` {${t.english}}` : "";
  return h("p", { class: "turn" },
    h("b", {}, `${t.speaker || "?"}${t.sentiment ? ` (${t.sentiment})` : ""}: `), `${t.text || ""}${extra}`);
}

function panel(i, sys, redraw) {
  const d = i[sys];
  const v = i.votes[sys];
  if (!d) return h("section", { class: "panel" }, h("h2", {}, SYSTEMS[sys]), h("p", { class: "muted" }, "Result pending…"));
  const note = h("input", { placeholder: "Note (optional): what was wrong?", value: v.my_note || "" });
  const vote = async (verdict) => {
    try {
      const r = await api("/api/review", { method: "POST", body: JSON.stringify({ id: i.id, system: sys, verdict, note: note.value }) });
      i.votes = (await r.json()).votes;
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred(verdict === "ok" ? "success" : "warning");
      redraw();
    } catch (e) { say("Could not save: " + e.message); }
  };
  return h("section", { class: "panel" },
    h("h2", {}, SYSTEMS[sys], d.secs ? h("small", { class: "muted" }, ` · ${d.secs}s`) : null),
    d.error ? h("p", { class: "err" }, "Error: " + d.error) : null,
    h("p", {}, h("b", {}, "Sentiment: "), d.sentiment || "-"),
    h("p", {}, h("b", {}, "Summary: "), d.summary || "-"),
    h("div", { class: "turns" }, (d.turns || []).map(turnLine)),
    h("div", { class: "vote" },
      h("button", { class: v.mine === "ok" ? "ok on" : "ok", onclick: () => vote("ok") }, "✅ Correct"),
      h("button", { class: v.mine === "bad" ? "bad on" : "bad", onclick: () => vote("bad") }, "❌ Wrong")),
    note,
    h("p", { class: "muted" }, `Team: ✅ ${v.ok} · ❌ ${v.bad}`),
    v.notes.length ? h("ul", { class: "notes" }, v.notes.map((n) => h("li", {}, n))) : null);
}

async function openItem(id) {
  const i = items.find((x) => x.id === id);
  if (!i) return renderList();
  if (tg) tg.BackButton.show();
  const audio = h("audio", { controls: true, preload: "none" });
  const cols = h("div", { class: "cols" });
  const redraw = () => cols.replaceChildren(panel(i, "pipeline", redraw), panel(i, "gemma", redraw));
  redraw();
  $app.replaceChildren(
    h("header", {},
      h("button", { class: "link", onclick: renderList }, "← All conversations"),
      h("h1", {}, `${i.kind === "call" ? "📞" : "🏪"} ${i.who}`),
      h("p", { class: "muted" }, `${i.store} · ${i.date} ${i.time}${i.duration ? " · " + i.duration : ""}`)),
    audio, cols);
  window.scrollTo(0, 0);
  try {
    audio.src = URL.createObjectURL(await (await api(`/api/audio/${i.id}`)).blob());
  } catch (e) {
    audio.replaceWith(h("p", { class: "muted" }, "Audio unavailable: " + e.message));
  }
}

async function load() {
  if (!INIT || !API) {
    $app.replaceChildren(h("p", { class: "empty" }, "Open this from the 📝 Review button in the Telegram group."));
    return;
  }
  tg.ready();
  tg.expand();
  tg.BackButton.onClick(renderList);
  try {
    items = (await (await api("/api/conversations")).json()).items;
  } catch (e) {
    $app.replaceChildren(h("p", { class: "empty" }, "Could not load conversations: " + e.message));
    return;
  }
  if (openId) openItem(openId);
  else renderList();
}

load();
