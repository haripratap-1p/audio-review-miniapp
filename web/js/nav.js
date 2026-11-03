// top bar with view tabs and stats, and the Calls / In-store tabs
import { state, SYSTEMS, has, isDone, notUsed, queue } from "./state.js?v=__V__";
import { h } from "./dom.js?v=__V__";
import { themeButton } from "./theme.js?v=__V__";
import { showReview, showDone } from "./review.js?v=__V__";
import { showList } from "./list.js?v=__V__";
import { showBenchmark } from "./benchmark.js?v=__V__";
import { showTeam } from "./team.js?v=__V__";

export function topbar(active) {
  const mine = state.items.filter((i) => i.kind === state.kind);
  const waiting = mine.filter((i) => SYSTEMS.some((s) => !has(i, s) && !notUsed(i, s))).length;
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
      SYSTEMS.length > 1 ? stat(waiting, "waiting for other models") : null));
}

export function kindTabs(active) {
  const openOf = (k) => state.items.filter((i) => i.kind === k && !isDone(i)).length;
  const kindTab = (k, text) => h("button", {
    class: "kind-tab", role: "tab", "aria-selected": String(state.kind === k),
    onclick: () => { state.kind = k; active === "all" ? showList() : queue().length ? showReview(queue()[0].id) : showDone(); },
  }, text, h("span", { class: "count" }, openOf(k)));
  return h("div", { class: "kind-tabs", role: "tablist", "aria-label": "Recording type" }, kindTab("call", "Calls"), kindTab("in-store", "In-store"));
}
