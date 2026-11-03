// Telegram Mini App: review store conversations. General users see our audio pipeline; the Tech team also sees Gemma and Gemini.
import { tg, state, queue } from "./state.js?v=__V__";
import { $app, skeleton, message, showError } from "./dom.js?v=__V__";
import { initTheme } from "./theme.js?v=__V__";
import { API, INIT, openId, loadList } from "./api.js?v=__V__";
import { showReview, showDone, showDesk } from "./review.js?v=__V__";

initTheme();

// switching between phone and PC widths re-renders the current view
matchMedia("(min-width: 1000px)").addEventListener("change", (e) => {
  if (!state.items.length) return;
  if (!e.matches) { $app.classList.remove("wide"); return state.current ? showReview(state.current) : showDone(); }
  showDesk(state.current);
});

export async function start() {
  if (!INIT || !API) return message("Open from Telegram", "Open this page from the pinned Review message in the Telegram group.");
  try { state.skipped = JSON.parse(sessionStorage.getItem("skipped") || "[]"); } catch {}
  $app.replaceChildren(skeleton());
  try {
    await loadList();
  } catch (e) {
    return showError(e, start);
  }
  const target = openId && state.items.find((i) => i.id === openId);
  target ? showReview(target.id) : queue().length ? showReview(queue()[0].id) : showDone();
}

const DESKTOP = ["tdesktop", "macos", "web", "weba", "webk", "unigram"];
if (tg) {
  tg.ready();
  tg.expand();
  // laptops / PCs: open full screen so the list + A/B/C columns fit; phones keep the normal sheet
  if (DESKTOP.includes(tg.platform) && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0") && tg.requestFullscreen) {
    try { tg.requestFullscreen(); } catch {}
  }
  if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
  tg.BackButton.onClick(() => (queue().length ? showReview(queue()[0].id) : showDone()));
}
start();
