// owner page: everyone's access and the Tech toggle
import { $app, h, toast, skeleton, showError } from "./dom.js?v=__V__";
import { fmtDate } from "./format.js?v=__V__";
import { api } from "./api.js?v=__V__";
import { topbar } from "./list.js?v=__V__";
import { go } from "./router.js?v=__V__";

const ACCESS = { owner: "Owner", tech: "Tech", cost: "Cost group", general: "Analysis team" };

export async function renderTeam() {
  $app.replaceChildren(topbar("team"), skeleton());
  let people;
  try {
    people = (await (await api("/api/team")).json()).people;
  } catch (e) {
    return showError(e, () => go("team"));
  }
  const render = () => $app.replaceChildren(topbar("team"),
    h("p", { class: "note pad" }, "Tech and cost-group members see every model and the Benchmark. Everyone else sees only the audio pipeline."),
    h("ul", { class: "list" }, people.map((p) => h("li", { class: "person" },
      h("div", {}, h("span", { class: "who-line" }, p.name), h("span", { class: "note" }, `${p.username ? "@" + p.username + ", " : ""}last opened ${fmtDate(p.last_seen.slice(0, 10))} ${p.last_seen.slice(11, 16)}`)),
      h("div", { class: "row" }, h("span", { class: "badge todo" }, ACCESS[p.access] || (p.owner ? "Owner" : p.access)), p.owner || p.access === "owner" ? null : h("button", {
        class: "switch", role: "switch", "aria-checked": String(p.tech), "aria-label": `Tech team: ${p.name}`,
        onclick: async () => {
          try {
            people = (await (await api("/api/team", { method: "POST", body: JSON.stringify({ id: p.id, tech: !p.tech }) })).json()).people;
            render();
            toast("Saved");
          } catch (e) {
            showError(e, () => go("team"));
          }
        },
      }, h("span", { class: "knob" }), "Tech"))))));
  render();
}
