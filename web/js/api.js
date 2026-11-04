// review server calls, list and detail loading, and the review session
import { tg, state, setLabels } from "./state.js?v=__V__";
import { toast, message } from "./dom.js?v=__V__";
import { createSession } from "./session.js?v=__V__";

const params = new URLSearchParams(location.search);
const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || params.get("tgWebAppStartParam") || "";
const [startSub, openId] = startParam.split("__");
const sub = startSub || params.get("api") || "";  // menu button passes the tunnel as ?api=
export const API = /^[a-z0-9-]+$/.test(sub) ? `https://${sub}.trycloudflare.com` : "";
export const INIT = (tg && tg.initData) || "";
export { openId };

export class ApiError extends Error {
  constructor(status, msg) { super(msg); this.status = status; }
}

export async function api(path, opts = {}) {
  let r;
  try {
    r = await fetch(API + path, { ...opts, headers: { "X-Init-Data": INIT, "Content-Type": "application/json" } });
  } catch {
    throw new ApiError(0, "offline");
  }
  if (!r.ok) throw new ApiError(r.status, (await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
  return r;
}

export async function loadList() {
  const data = await (await api("/api/conversations")).json();
  state.items = data.items;
  state.role = data.role || "general";
  state.isOwner = !!data.is_owner;
  setLabels(data.labels || { pipeline: "Audio pipeline" });
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

export function getDetail(id) {
  if (!state.details.has(id)) {
    state.details.set(id, api(`/api/conversation/${id}`).then((r) => r.json()).catch((e) => { state.details.delete(id); throw e; }));
  }
  return state.details.get(id);
}

export function getAudio(id) {
  if (!state.audio.has(id)) {
    state.audio.set(id, api(`/api/audio/${id}`).then((r) => r.blob()).then((b) => URL.createObjectURL(b))
      .catch((e) => { state.audio.delete(id); throw e; }));
  }
  return state.audio.get(id);
}

export function prefetch(id) {
  if (!id) return;
  getDetail(id).catch(() => {});
  getAudio(id).catch(() => {});
}

// votes, drafts and undo live in the session; this wires it to the browser
let store = null;
try { store = localStorage; } catch {}
export const session = createSession({
  fetch: (...a) => fetch(...a), base: API, initData: INIT, storage: store, tg, state,
  userId: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.id) || "",
});
session.onChange((e) => {
  if (e.toast) toast(e.toast);
  if (e.expired) message("Reviews waiting", `Session expired: close and reopen from the pinned message; ${e.expired} review${e.expired === 1 ? "" : "s"} will be sent.`);
});
