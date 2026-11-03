// all conversations grouped by arrival day: phone page and PC sidebar
import { tg, state, SYSTEMS, SHORT, has, isDone, notUsed } from "./state.js?v=__V__";
import { $app, h, badge, hideToast } from "./dom.js?v=__V__";
import { arrDay, dayLabel, listWhen, verdictText } from "./format.js?v=__V__";
import { themeButton } from "./theme.js?v=__V__";
import { stopAudio } from "./player.js?v=__V__";
import { topbar, kindTabs } from "./nav.js?v=__V__";
import { wide, showReview, showDesk } from "./review.js?v=__V__";
import { showBenchmark } from "./benchmark.js?v=__V__";
import { showTeam } from "./team.js?v=__V__";

export function showList() {
  if (wide()) return showDesk(state.current);
  $app.classList.remove("page");
  stopAudio();
  hideToast();
  if (tg) tg.BackButton.show();
  const filters = [["all", "All"], ["todo", "To review"]];
  const keep = (i) => i.kind === state.kind && (state.filter === "all" || !isDone(i));
  const days = new Map();
  for (const i of state.items.filter(keep)) days.set(arrDay(i), [...(days.get(arrDay(i)) || []), i]);
  const rows = [...days].map(([date, list]) => h("section", { class: "day" },
    h("h2", {}, dayLabel(date)),
    h("ul", { class: "list" }, list.map((i) => h("li", {}, h("button", { onclick: () => showReview(i.id) },
      h("span", { class: "who-line" }, i.who),
      h("span", { class: "note" }, `${listWhen(i)}${i.duration ? `, ${i.duration}` : ""}`),
      h("span", { class: "marks" },
        SYSTEMS.map((s) => h("span", {}, `${SHORT[s]} `, has(i, s) ? badge(i.mine[s], verdictText(i.mine[s])) : h("span", { class: "badge todo" }, notUsed(i, s) ? "N/A" : "Pending"))))))))));
  $app.replaceChildren(topbar("all"),
    h("div", { class: "chips filters", role: "group", "aria-label": "Filter" },
      filters.map(([k, text]) => h("button", { class: "chip", "aria-pressed": String(state.filter === k), onclick: () => { state.filter = k; showList(); } }, text))),
    ...(rows.length ? rows : [h("p", { class: "note pad" }, "No conversations match this filter.")]));
}

export function sidebarList(selectedId) {
  const filters = [["all", "All"], ["todo", "To review"]];
  const keep = (i) => i.kind === state.kind && (state.filter === "all" || !isDone(i));
  const days = new Map();
  for (const i of state.items.filter(keep)) days.set(arrDay(i), [...(days.get(arrDay(i)) || []), i]);
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
        h("span", { class: "note" }, `${listWhen(i)}${i.duration ? `, ${i.duration}` : ""}`),
        h("span", { class: "marks" },
          SYSTEMS.map((s) => has(i, s) ? badge(i.mine[s], `${SHORT[s]} ${verdictText(i.mine[s]).toLowerCase()}`) : h("span", { class: "badge todo" }, `${SHORT[s]} ${notUsed(i, s) ? "N/A" : "pending"}`)))))))))
      : h("p", { class: "note pad" }, "Nothing here for this filter."));
}
