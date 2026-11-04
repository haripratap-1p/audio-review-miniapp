// shared app state, the systems this user may see, and queue rules
export const tg = window.Telegram && window.Telegram.WebApp;

// which systems and names this user may see come from the server (role-based)
export let SYSTEMS = ["pipeline"];
export let LABEL = { pipeline: "Audio pipeline" };
export function setLabels(labels) {
  LABEL = labels;
  SYSTEMS = Object.keys(LABEL);
}
export const SHORT = { pipeline: "Pipeline", gemma: "Gemma", gemini: "Gemini", lfm: "LFM3" };
export const REASONS = ["Wrong words", "Wrong speakers", "Wrong mood", "Missing parts", "Other"];

export const state = {
  items: [], total: 0, ready: 0, teamPipeline: 0, myToday: 0, filter: "all", kind: "call",
  skipped: [], details: new Map(), audio: new Map(),
};

// a system skipped because it doesn't support the conversation's language (LFM3: English only)
export const notUsed = (i, s) => (i.na || []).includes(s);
export const missingText = (i, s) => (notUsed(i, s) ? `${LABEL[s]} is not used for this language.` : `${LABEL[s]} isn't ready for this conversation yet.`);

// a conversation is still open for me until every available result has my verdict
export const has = (i, s) => (i.avail ? i.avail[s] : s === "pipeline" || (s === "gemma" && i.ready));
export const isDone = (i) => SYSTEMS.every((s) => !has(i, s) || i.mine[s]);
export const nextOpen = (i, after) => SYSTEMS.find((s) => s !== after && has(i, s) && !i.mine[s]);
export function queue() {
  const open = state.items.filter((i) => i.kind === state.kind && !isDone(i));
  return [...open.filter((i) => !state.skipped.includes(i.id)), ...open.filter((i) => state.skipped.includes(i.id))];
}
