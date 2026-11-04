// all conversations grouped by arrival day (phone page and PC sidebar), the top bar and the Calls / In-store tabs
import { state, SYSTEMS, SHORT, has, isDone, notUsed, queue } from "./state.js?v=__V__";
import { $app, h, badge } from "./dom.js?v=__V__";
import { arrDay, dayLabel, listWhen, verdictText } from "./format.js?v=__V__";
import { themeButton } from "./theme.js?v=__V__";
import { go } from "./router.js?v=__V__";

export function topbar(active) {
  const mine = state.items.filter((i) => i.kind === state.kind);
  const waiting = mine.filter((i) => SYSTEMS.some((s) => !has(i, s) && !notUsed(i, s))).length;
  const stat = (n, label) => h("span", {}, h("b", {}, n), ` ${label}`);
  const tab = (key, text, screen) => h("button", { class: "seg-btn", "aria-pressed": String(active === key), onclick: () => go(screen) }, text);

  const page = ["benchmark", "team"].includes(active);
  return h("header", { class: "top" },
    h("div", { class: "row between" }, h("div", { class: "top-left" }, h("h1", {}, "Review"), themeButton())),
    h("div", { class: "seg nav", role: "group", "aria-label": "View" },
      tab("queue", "Queue", "next"), tab("all", "All", "list"),
      state.role === "tech" ? tab("benchmark", "Benchmark", "benchmark") : null,
      state.isOwner ? tab("team", "Team", "team") : null),
    page ? null : kindTabs(active),
    page ? null : h("p", { class: "stats" }, stat(queue().length, "for you"), stat(mine.filter((i) => i.mine.pipeline).length, "checked by you"),
      SYSTEMS.length > 1 ? stat(waiting, "waiting for other models") : null));
}

function kindTabs(active) {
  const openOf = (k) => state.items.filter((i) => i.kind === k && !isDone(i)).length;
  const kindTab = (k, text) => h("button", {
    class: "kind-tab", role: "tab", "aria-selected": String(state.kind === k),
    onclick: () => { state.kind = k; go(active === "all" ? "list" : "next"); },
  }, text, h("span", { class: "count" }, openOf(k)));
  return h("div", { class: "kind-tabs", role: "tablist", "aria-label": "Recording type" }, kindTab("call", "Calls"), kindTab("in-store", "In-store"));
}

const FILTERS = [["all", "All"], ["todo", "To review"]];

function byDay() {
  const keep = (i) => i.kind === state.kind && (state.filter === "all" || !isDone(i));
  const days = new Map();
  for (const i of state.items.filter(keep)) days.set(arrDay(i), [...(days.get(arrDay(i)) || []), i]);
  return days;
}

const filterChips = (repaint) => h("div", { class: "chips filters", role: "group", "aria-label": "Filter" },
  FILTERS.map(([k, text]) => h("button", { class: "chip", "aria-pressed": String(state.filter === k), onclick: () => { state.filter = k; repaint(); } }, text)));

export function renderList() {
  const rows = [...byDay()].map(([date, list]) => h("section", { class: "day" },
    h("h2", {}, dayLabel(date)),
    h("ul", { class: "list" }, list.map((i) => h("li", {}, h("button", { onclick: () => go("review", i.id) },
      h("span", { class: "who-line" }, i.who),
      h("span", { class: "note" }, `${listWhen(i)}${i.duration ? `, ${i.duration}` : ""}`),
      h("span", { class: "marks" },
        SYSTEMS.map((s) => h("span", {}, `${SHORT[s]} `, has(i, s) ? badge(i.mine[s], verdictText(i.mine[s])) : h("span", { class: "badge todo" }, notUsed(i, s) ? "N/A" : "Pending"))))))))));
  $app.replaceChildren(topbar("all"), filterChips(() => go("list")),
    ...(rows.length ? rows : [h("p", { class: "note pad" }, "No conversations match this filter.")]));
}

export function sidebarList(selectedId) {
  const days = byDay();
  return h("aside", { class: "side" },
    h("div", { class: "top-left" }, h("h1", {}, "Review"), themeButton()),
    state.role === "tech" ? h("div", { class: "row side-links" },
      h("button", { class: "link", onclick: () => go("benchmark") }, "Benchmark"),
      state.isOwner ? h("button", { class: "link", onclick: () => go("team") }, "Team") : null) : null,
    kindTabs("queue"),
    filterChips(() => go("review", selectedId)),
    days.size ? [...days].map(([date, list]) => h("section", { class: "day" },
      h("h2", {}, dayLabel(date)),
      h("ul", { class: "list" }, list.map((i) => h("li", {}, h("button", { "aria-current": String(i.id === selectedId), onclick: () => go("review", i.id) },
        h("span", { class: "who-line" }, i.who),
        h("span", { class: "note" }, `${listWhen(i)}${i.duration ? `, ${i.duration}` : ""}`),
        h("span", { class: "marks" },
          SYSTEMS.map((s) => has(i, s) ? badge(i.mine[s], `${SHORT[s]} ${verdictText(i.mine[s]).toLowerCase()}`) : h("span", { class: "badge todo" }, `${SHORT[s]} ${notUsed(i, s) ? "N/A" : "pending"}`)))))))))
      : h("p", { class: "note pad" }, "Nothing here for this filter."));
}
