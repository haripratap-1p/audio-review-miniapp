// screen changes: the steps every screen shares live here; screens only render and call go()
const STEPS = {
  review: [false, ""], desk: [false, "wide"], done: [false, ""], refresh: [false, ""],
  list: [true, ""], benchmark: [true, "page"], team: [true, "page"],
};
let ctx = null;

// ctx: { screens: {name: render(arg)}, app, tg, state, queue, wide, stopAudio, hideToast }
export function initRouter(c) { ctx = c; }

export function go(screen, arg) {
  const { screens, app, tg, state, queue, wide, stopAudio, hideToast } = ctx;
  if (screen === "next") [screen, arg] = queue().length ? ["review", queue()[0].id] : ["done"];
  if (wide() && ["review", "list", "done"].includes(screen)) [screen, arg] = ["desk", screen === "list" ? state.current : arg];
  const [back, cls] = STEPS[screen];
  stopAudio();
  hideToast();
  if (tg) back ? tg.BackButton.show() : tg.BackButton.hide();
  app.classList.remove("wide", "page");
  if (cls) app.classList.add(cls);
  return screens[screen](arg);
}
