// element builder, icons, toast, sheets and full-screen messages
import { tg, REASONS } from "./state.js?v=__V__";

export const $app = document.getElementById("app");
const $toast = document.getElementById("toast");

export function h(tag, attrs = {}, ...kids) {
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
export function icon(name) {
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

export const badge = (v, text) => h("span", { class: `badge ${v || "todo"}` }, v === "ok" ? icon("check") : v === "bad" ? icon("cross") : null, text);

export const haptic = (kind) => tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(kind);

export function toast(text, action) {
  $toast.replaceChildren(...[h("span", {}, text), action && h("button", { class: "link", onclick: () => { hideToast(); action.run(); } }, action.label)].filter(Boolean));
  $toast.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(hideToast, action ? 5000 : 2500);
}
export function hideToast() { $toast.hidden = true; }

export const skeleton = () => h("div", { class: "skeleton", "aria-busy": "true", "aria-label": "Loading" }, h("span"), h("span"), h("span"));

export function message(title, text, button) {
  if (tg) tg.BackButton.hide();
  $app.replaceChildren(h("section", { class: "message" },
    h("h1", {}, title), h("p", {}, text), button ? h("button", { class: "btn primary", onclick: button.run }, button.label) : null));
}

export function showError(e, retry) {
  if (e.status === 401) return message("Session expired", "Close this window and open it again from the pinned Review message.");
  if (e.status === 403) return message("Not allowed", "Only members of the review group can review conversations.");
  if (e.status === 0) return message("No connection", "Can't reach the review server. Check your internet and try again.", { label: "Try again", run: retry });
  message("Something went wrong", "The review server couldn't load this. Try again in a minute.", { label: "Try again", run: retry });
}

export function confirmSheet(title, lines, okLabel, okClass, onOk) {
  const close = () => sheet.remove();
  const ok = h("button", { class: `btn ${okClass}`, onclick: () => { ok.disabled = true; close(); onOk(); } }, okLabel);
  const sheet = h("div", { class: "sheet-bg", onclick: (e) => e.target === sheet && close() },
    h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "confirm-title" },
      h("h2", { id: "confirm-title" }, title),
      lines.filter(Boolean).map((l) => h("p", { class: l.warn ? "warn" : "summary-line" }, l.text || l)),
      h("div", { class: "row" }, h("button", { class: "btn quiet", onclick: close }, "Go back"), ok)));
  document.body.append(sheet);
  ok.focus();
}

export function reasonSheet(onSave, title = "What was wrong?", saveText = "Save as wrong") {
  const picked = new Set();
  const other = h("input", { type: "text", maxlength: 200, placeholder: "Anything else? (optional)", "aria-label": "Other reason" });
  const close = () => sheet.remove();
  const sheet = h("div", { class: "sheet-bg", onclick: (e) => e.target === sheet && close() },
    h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "sheet-title" },
      h("h2", { id: "sheet-title" }, title),
      h("p", { class: "note" }, "Tap all that apply."),
      h("div", { class: "chips" }, REASONS.map((r) => h("button", {
        class: "chip", "aria-pressed": "false",
        onclick: (e) => { picked.has(r) ? picked.delete(r) : picked.add(r); e.currentTarget.setAttribute("aria-pressed", String(picked.has(r))); },
      }, r))),
      other,
      h("div", { class: "row" },
        h("button", { class: "btn quiet", onclick: close }, "Cancel"),
        h("button", { class: "btn bad solid", onclick: () => { close(); onSave([...picked, other.value.trim()].filter(Boolean).join(", ")); } }, saveText))));
  document.body.append(sheet);
  sheet.querySelector(".chip").focus();
}
