// screen router: shared steps per screen, desk redirect on wide screens, next in queue else done
import { test } from "node:test";
import assert from "node:assert/strict";
import { initRouter, go } from "../js/router.js?v=__V__";

function setup({ wide = false, queue = [], current } = {}) {
  const calls = [], log = [];
  const classes = new Set(["wide", "page"]);
  const app = { classList: { add: (c) => classes.add(c), remove: (...c) => c.forEach((x) => classes.delete(x)) } };
  const tg = { BackButton: { visible: null, show() { this.visible = true; }, hide() { this.visible = false; } } };
  const screen = (name) => (arg) => calls.push([name, arg]);
  const names = ["review", "desk", "done", "list", "benchmark", "team", "refresh"];
  initRouter({
    app, tg, state: { current }, queue: () => queue, wide: () => wide,
    stopAudio: () => log.push("stopAudio"), hideToast: () => log.push("hideToast"),
    screens: Object.fromEntries(names.map((n) => [n, screen(n)])),
  });
  return { calls, log, classes, tg };
}

test("every screen change stops audio and hides the toast", () => {
  for (const name of ["review", "done", "list", "benchmark", "team", "refresh"]) {
    const { log } = setup();
    go(name);
    assert.deepEqual(log, ["stopAudio", "hideToast"], name);
  }
});

test("pages show the back button and set the page layout", () => {
  for (const name of ["benchmark", "team"]) {
    const { calls, classes, tg } = setup();
    go(name);
    assert.deepEqual(calls, [[name, undefined]]);
    assert.deepEqual([...classes], ["page"]);
    assert.equal(tg.BackButton.visible, true);
  }
});

test("the list shows the back button with no layout class", () => {
  const { classes, tg } = setup();
  go("list");
  assert.deepEqual([...classes], []);
  assert.equal(tg.BackButton.visible, true);
});

test("review and done hide the back button", () => {
  for (const name of ["review", "done"]) {
    const { classes, tg } = setup();
    go(name, "c1");
    assert.deepEqual([...classes], []);
    assert.equal(tg.BackButton.visible, false);
  }
});

test("next opens the first queued conversation, else done", () => {
  const a = setup({ queue: [{ id: "c4" }, { id: "c5" }] });
  go("next");
  assert.deepEqual(a.calls, [["review", "c4"]]);
  const b = setup();
  go("next");
  assert.deepEqual(b.calls, [["done", undefined]]);
});

test("on wide screens review, list and done open the desk", () => {
  const { calls, classes, tg } = setup({ wide: true, current: "c2", queue: [{ id: "c9" }] });
  go("review", "c1");
  go("list");
  go("done");
  go("next");
  assert.deepEqual(calls, [["desk", "c1"], ["desk", "c2"], ["desk", undefined], ["desk", "c9"]]);
  assert.deepEqual([...classes], ["wide"]);
  assert.equal(tg.BackButton.visible, false);
  go("benchmark");
  assert.deepEqual([...classes], ["page"]);
});

test("works without Telegram", () => {
  const { calls } = setup();
  initRouter({ app: { classList: { add() {}, remove() {} } }, tg: null, state: {}, queue: () => [], wide: () => false,
    stopAudio() {}, hideToast() {}, screens: { team: (a) => calls.push(["team", a]) } });
  go("team");
  assert.deepEqual(calls, [["team", undefined]]);
});
