// recording player; only one recording plays at a time and any screen change stops it
import { h, icon } from "./dom.js?v=__V__";
import { getAudio } from "./api.js?v=__V__";

export function stopAudio() {
  if (player.active) player.active.pause();
}

export function player(id) {
  stopAudio();
  const audio = new Audio();
  player.active = audio;
  const btn = h("button", { class: "play", disabled: true, "aria-label": "Play recording" }, icon("play"));
  const speed = h("button", { class: "chip", disabled: true, "aria-label": "Playback speed" }, "1×");
  const fill = h("span");
  const track = h("div", { class: "track", "aria-hidden": "true" }, fill);
  const time = h("span", { class: "time" }, "0:00");
  const fmt = (s) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00");
  const paint = () => {
    btn.replaceChildren(icon(audio.paused ? "play" : "pause"));
    btn.setAttribute("aria-label", audio.paused ? "Play recording" : "Pause recording");
    fill.style.width = audio.duration ? `${(audio.currentTime / audio.duration) * 100}%` : "0";
    time.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
  };
  ["play", "pause", "timeupdate", "loadedmetadata", "ended"].forEach((ev) => audio.addEventListener(ev, paint));
  btn.addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
  speed.addEventListener("click", () => {
    audio.playbackRate = audio.playbackRate === 1 ? 1.5 : 1;
    speed.textContent = `${audio.playbackRate}×`;
  });
  track.addEventListener("click", (e) => {
    const r = track.getBoundingClientRect();
    if (audio.duration) audio.currentTime = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * audio.duration;
  });
  getAudio(id).then((url) => { audio.src = url; btn.disabled = speed.disabled = false; paint(); })
    .catch(() => { time.textContent = "Recording unavailable"; });
  const box = h("section", { class: "player" }, btn, track, time, speed);
  box.stop = () => audio.pause();
  return box;
}
