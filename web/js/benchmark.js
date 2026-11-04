// Tech team benchmark: % correct per system, calls vs in-store, daily trend, reviewers
import { $app, h, skeleton, showError } from "./dom.js?v=__V__";
import { fmtDate } from "./format.js?v=__V__";
import { api } from "./api.js?v=__V__";
import { topbar } from "./list.js?v=__V__";
import { go } from "./router.js?v=__V__";

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

export async function renderBenchmark() {
  $app.replaceChildren(topbar("benchmark"), skeleton());
  let b;
  try {
    b = await (await api("/api/benchmark")).json();
  } catch (e) {
    return showError(e, () => go("benchmark"));
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
