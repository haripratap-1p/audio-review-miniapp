// date filter: a month calendar where only days with recordings can be picked
import { h } from "./dom.js?v=__V__";
import { fmtDate, monthGrid, monthLabel, todayIst } from "./format.js?v=__V__";

const WEEK = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

// counts: Map "YYYY-MM-DD" -> recordings that day; onPick(day or null for all dates)
export function calendarSheet(counts, picked, onPick) {
  const months = [...new Set([...counts.keys()].map((d) => d.slice(0, 7)))].sort();
  let at = (picked || [...counts.keys()].sort().at(-1) || todayIst()).slice(0, 7);
  if (months.length && !months.includes(at)) at = months.at(-1);
  const close = () => { sheet.remove(); document.removeEventListener("keydown", esc); };
  const esc = (e) => e.key === "Escape" && close();
  const pick = (d) => { close(); onPick(d); };
  const body = h("div", { class: "cal-wrap" });
  const step = (by) => { at = months[months.indexOf(at) + by]; paint(); };
  const day = (d) => {
    if (!d) return h("span", { "aria-hidden": "true" });
    const n = counts.get(d) || 0, num = Number(d.slice(8));
    if (!n) return h("button", { class: "cal-day", disabled: true, "aria-label": `${fmtDate(d)}, no recordings` }, num);
    return h("button", {
      class: "cal-day has", "aria-pressed": String(d === picked), "aria-label": `${fmtDate(d)}, ${n} recording${n === 1 ? "" : "s"}`,
      onclick: () => pick(d),
    }, num, h("small", {}, n));
  };
  const paint = () => {
    const i = months.indexOf(at);
    body.replaceChildren(
      h("div", { class: "row between cal-head" },
        h("button", { class: "cal-nav", "aria-label": "Earlier month", disabled: i <= 0, onclick: () => step(-1) }, "‹"),
        h("h2", { id: "cal-title", "aria-live": "polite" }, monthLabel(at)),
        h("button", { class: "cal-nav", "aria-label": "Later month", disabled: i < 0 || i >= months.length - 1, onclick: () => step(1) }, "›")),
      h("div", { class: "cal" }, WEEK.map((w) => h("span", { class: "cal-wd", "aria-hidden": "true" }, w)), monthGrid(at).map(day)));
    (body.querySelector(".cal-day[aria-pressed='true']") || body.querySelector(".cal-day.has") || body.querySelector("button:not([disabled])"))?.focus();
  };
  const sheet = h("div", { class: "sheet-bg", onclick: (e) => e.target === sheet && close() },
    h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "cal-title" },
      h("p", { class: "note" }, "Days with recordings are highlighted. Tap one to show only that day."),
      body,
      h("div", { class: "row" },
        h("button", { class: "btn quiet", onclick: close }, "Cancel"),
        h("button", { class: "btn primary", onclick: () => pick(null) }, "Show all dates"))));
  document.body.append(sheet);
  document.addEventListener("keydown", esc);
  paint();
}
