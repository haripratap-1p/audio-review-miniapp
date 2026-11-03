// white or dark theme; the reviewer's choice wins, else Telegram's
import { tg } from "./state.js?v=__V__";
import { h, icon } from "./dom.js?v=__V__";

const PAPER = { light: "#F5F5F7", dark: "#0E0E10" };  // same values as --paper in style.css

function savedTheme() {
  try { return localStorage.getItem("theme"); } catch { return null; }
}
function applyTheme() {
  const pick = savedTheme();
  const dark = pick ? pick === "dark" : tg && tg.colorScheme ? tg.colorScheme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const mode = dark ? "dark" : "light";
  document.documentElement.dataset.theme = mode;
  try { tg.setHeaderColor(PAPER[mode]); tg.setBackgroundColor(PAPER[mode]); } catch {}
  document.querySelectorAll(".theme-btn").forEach(paintThemeButton);
}
function paintThemeButton(btn) {
  const dark = document.documentElement.dataset.theme === "dark";
  btn.replaceChildren(icon(dark ? "sun" : "moon"));
  btn.setAttribute("aria-label", dark ? "Switch to white theme" : "Switch to dark theme");
}
export function themeButton() {
  const btn = h("button", { class: "theme-btn", onclick: () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try { localStorage.setItem("theme", next); } catch {}
    applyTheme();
  } });
  paintThemeButton(btn);
  return btn;
}

export function initTheme() {
  applyTheme();
  if (tg) tg.onEvent("themeChanged", applyTheme);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
}
