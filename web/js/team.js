// owner page: who is in the Tech team
import { tg } from "./state.js?v=__V__";
import { $app, h, toast, hideToast, skeleton, showError } from "./dom.js?v=__V__";
import { fmtDate } from "./format.js?v=__V__";
import { api } from "./api.js?v=__V__";
import { stopAudio } from "./player.js?v=__V__";
import { topbar } from "./nav.js?v=__V__";

export async function showTeam() {
  stopAudio();
  hideToast();
  if (tg) tg.BackButton.show();
  $app.classList.remove("wide");
  $app.classList.add("page");
  $app.replaceChildren(topbar("team"), skeleton());
  let people;
  try {
    people = (await (await api("/api/team")).json()).people;
  } catch (e) {
    return showError(e, showTeam);
  }
  const render = () => $app.replaceChildren(topbar("team"),
    h("p", { class: "note pad" }, "Tech team members see Gemma and Gemini results and the benchmark. Everyone else sees only the audio pipeline."),
    h("ul", { class: "list" }, people.map((p) => h("li", { class: "person" },
      h("div", {}, h("span", { class: "who-line" }, p.name), h("span", { class: "note" }, `${p.username ? "@" + p.username + ", " : ""}last opened ${fmtDate(p.last_seen.slice(0, 10))} ${p.last_seen.slice(11, 16)}`)),
      p.owner ? h("span", { class: "badge todo" }, "Owner") : h("button", {
        class: "switch", role: "switch", "aria-checked": String(p.tech), "aria-label": `Tech team: ${p.name}`,
        onclick: async () => {
          try {
            people = (await (await api("/api/team", { method: "POST", body: JSON.stringify({ id: p.id, tech: !p.tech }) })).json()).people;
            render();
            toast("Saved");
          } catch (e) {
            showError(e, showTeam);
          }
        },
      }, h("span", { class: "knob" }), p.tech ? "Tech team" : "General")))));
  render();
}
