// Telegram Mini App: review store conversations. General users see our audio pipeline; the Tech team also sees Gemma and Gemini.
import { tg, state, queue } from "./state.js?v=__V__";
import { $app, skeleton, message, showError, hideToast } from "./dom.js?v=__V__";
import { initTheme } from "./theme.js?v=__V__";
import { API, INIT, openId, loadList, session } from "./api.js?v=__V__";
import { stopAudio } from "./player.js?v=__V__";
import { initRouter, go } from "./router.js?v=__V__";
import { renderReview, renderDesk, renderDone } from "./review.js?v=__V__";
import { renderList } from "./list.js?v=__V__";
import { renderBenchmark } from "./benchmark.js?v=__V__";
import { renderTeam } from "./team.js?v=__V__";

async function start() {
  if (!INIT || !API) return message("Open from Telegram", "Open this page from the pinned Review message in the Telegram group.");
  try { state.skipped = JSON.parse(sessionStorage.getItem("skipped") || "[]"); } catch {}
  $app.replaceChildren(skeleton());
  try {
    await loadList();
  } catch (e) {
    return showError(e, () => go("refresh"));
  }
  session.start();
  const target = openId && state.items.find((i) => i.id === openId);
  target ? go("review", target.id) : go("next");
}

const wideQuery = matchMedia("(min-width: 1000px)");
initRouter({
  app: $app, tg, state, queue, stopAudio, hideToast, wide: () => wideQuery.matches,
  screens: { review: renderReview, desk: renderDesk, done: renderDone, list: renderList, benchmark: renderBenchmark, team: renderTeam, refresh: start },
});

initTheme();

// switching between phone and PC widths re-renders the current view
wideQuery.addEventListener("change", () => { if (state.items.length) go("review", state.current); });

const DESKTOP = ["tdesktop", "macos", "web", "weba", "webk", "unigram"];
if (tg) {
  tg.ready();
  tg.expand();
  // laptops / PCs: open full screen so the list + A/B/C columns fit; phones keep the normal sheet
  if (DESKTOP.includes(tg.platform) && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0") && tg.requestFullscreen) {
    try { tg.requestFullscreen(); } catch {}
  }
  if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
  tg.BackButton.onClick(() => go("next"));
}
go("refresh");
