// review session: drafts, submit payload, undo, retry, expired-session retention, discards, today's count
import { test } from "node:test";
import assert from "node:assert/strict";
import { createSession } from "../js/session.js?v=__V__";

function memoryStorage(seed = {}) {
  const data = { ...seed };
  return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); }, removeItem: (k) => { delete data[k]; } };
}

// replies: list of status codes (0 = network error) used in order, then 200
function setup({ replies = [], storage = memoryStorage(), mine = {}, myToday = 0 } = {}) {
  const posts = [], events = [], waits = [];
  const tg = { closing: false, enableClosingConfirmation() { this.closing = true; }, disableClosingConfirmation() { this.closing = false; } };
  const state = { items: [{ id: "c1", mine: { ...mine } }, { id: "c2", mine: {} }], details: new Map([["c1", "cached"]]), myToday };
  const fetch = async (url, opts) => {
    const status = replies.length ? replies.shift() : 200;
    if (status === 0) throw new TypeError("offline");
    posts.push({ url, body: JSON.parse(opts.body), headers: opts.headers, status });
    const body = status === 409 ? { error: "This result isn't ready" } : status === 400 ? { error: "bad line marks" } : {};
    return { ok: status < 300, status, json: async () => body };
  };
  const s = createSession({ fetch, base: "https://x.test", initData: "init", storage, tg, userId: 7, state, wait: async (ms) => { waits.push(ms); } });
  s.onChange((e) => events.push(e));
  return { s, posts, events, waits, tg, state, storage };
}

test("mark and clear line drafts; closing guard follows drafts", () => {
  const { s, tg } = setup();
  s.mark("c1", "pipeline", "0", "ok", "");
  s.mark("c1", "pipeline", "1", "bad", "Wrong words");
  assert.deepEqual(s.draft("c1", "pipeline"), { 0: { verdict: "ok", note: "" }, 1: { verdict: "bad", note: "Wrong words" } });
  assert.equal(tg.closing, true);
  s.mark("c1", "pipeline", "0", null);
  s.mark("c1", "pipeline", "1", null);
  assert.deepEqual(s.draft("c1", "pipeline"), {});
  assert.equal(tg.closing, false);
});

test("submit sends verdict, note and line marks, then clears the draft", async () => {
  const { s, posts, state, tg } = setup();
  s.mark("c1", "pipeline", "2", "bad", "Missing parts");
  await s.submit("c1", "pipeline", "bad", "Wrong speakers");
  assert.equal(posts.length, 1);
  assert.equal(posts[0].url, "https://x.test/api/review");
  assert.equal(posts[0].headers["X-Init-Data"], "init");
  assert.deepEqual(posts[0].body, { id: "c1", system: "pipeline", verdict: "bad", note: "Wrong speakers", lines: { 2: { verdict: "bad", note: "Missing parts" } } });
  assert.equal(state.items[0].mine.pipeline, "bad");
  assert.deepEqual(s.draft("c1", "pipeline"), {});
  assert.deepEqual(s.lines("c1", "pipeline", { lines: { pipeline: { mine: {}, team: { 2: { ok: 1, bad: 0 } } } } }),
    { mine: { 2: { verdict: "bad", note: "Missing parts" } }, team: { 2: { ok: 1, bad: 0 } } });
  assert.equal(state.details.has("c1"), false);
  assert.equal(s.pending(), 0);
  assert.equal(tg.closing, false);
});

test("undo sends clear and empties my line marks", async () => {
  const { s, posts, state } = setup();
  s.mark("c1", "pipeline", "0", "ok", "");
  await s.submit("c1", "pipeline", "ok", "");
  await s.undo("c1", "pipeline");
  assert.deepEqual(posts[1].body, { id: "c1", system: "pipeline", verdict: "clear", note: "" });
  assert.equal(state.items[0].mine.pipeline, null);
  assert.deepEqual(s.lines("c1", "pipeline", { lines: { pipeline: { mine: { 0: { verdict: "ok" } }, team: {} } } }).mine, {});
});

test("network errors and server errors are retried until saved", async () => {
  const { s, posts, events, waits, storage } = setup({ replies: [0, 500] });
  await s.submit("c1", "pipeline", "ok", "");
  assert.equal(posts.length, 2);
  assert.equal(posts.at(-1).status, 200);
  assert.deepEqual(waits, [5000, 5000]);
  assert.equal(events.filter((e) => e.toast).length, 2);
  assert.equal(s.pending(), 0);
  assert.equal(storage.getItem("pendingVotes:7"), null);
});

test("401 keeps unsent votes per user and resends them on the next start", async () => {
  const storage = memoryStorage();
  const first = setup({ replies: [401], storage });
  await first.s.submit("c1", "pipeline", "ok", "");
  assert.deepEqual(first.events.find((e) => e.expired), { expired: 1 });
  assert.equal(first.s.pending(), 1);
  assert.equal(first.tg.closing, true);
  assert.equal(JSON.parse(storage.getItem("pendingVotes:7")).length, 1);

  const next = setup({ storage });
  await next.s.start();
  assert.equal(next.state.items[0].mine.pipeline, "ok");
  assert.equal(next.state.myToday, 1);
  assert.deepEqual(next.posts.map((p) => p.body.verdict), ["ok"]);
  assert.equal(storage.getItem("pendingVotes:7"), null);
  assert.equal(next.s.pending(), 0);
});

test("403 also keeps the votes", async () => {
  const { s, events, storage } = setup({ replies: [403] });
  await s.submit("c1", "pipeline", "ok", "");
  assert.ok(events.some((e) => e.expired === 1));
  assert.ok(storage.getItem("pendingVotes:7"));
});

test("409 drops the vote, rolls it back and shows the server message", async () => {
  const { s, events, state, storage } = setup({ replies: [409] });
  await s.submit("c1", "pipeline", "ok", "");
  assert.ok(events.some((e) => e.toast === "This result isn't ready"));
  assert.equal(s.pending(), 0);
  assert.equal(state.items[0].mine.pipeline, null);
  assert.equal(state.myToday, 0);
  assert.equal(storage.getItem("pendingVotes:7"), null);
});

test("400 drops the vote and the next one is still sent", async () => {
  const { s, posts, events } = setup({ replies: [400] });
  const sending = s.submit("c1", "pipeline", "ok", "");
  s.submit("c2", "pipeline", "bad", "x");
  await sending;
  assert.ok(events.some((e) => e.toast && e.toast.includes("bad line marks")));
  assert.deepEqual(posts.map((p) => [p.body.id, p.status]), [["c1", 400], ["c2", 200]]);
  assert.equal(s.pending(), 0);
});

test("myToday counts a conversation once and goes back down on undo", async () => {
  const { s, state } = setup({ myToday: 3 });
  await s.submit("c1", "pipeline", "ok", "");
  assert.equal(state.myToday, 4);
  await s.submit("c1", "gemma", "ok", "");
  assert.equal(state.myToday, 4);
  await s.undo("c1", "gemma");
  assert.equal(state.myToday, 4);
  await s.undo("c1", "pipeline");
  assert.equal(state.myToday, 3);
  await s.submit("c1", "pipeline", "bad", "");
  assert.equal(state.myToday, 4);
});

test("revisiting an already reviewed conversation does not count it again", async () => {
  const { s, state } = setup({ mine: { pipeline: "ok" }, myToday: 1 });
  await s.submit("c1", "gemma", "ok", "");
  assert.equal(state.myToday, 1);
});

test("storage that throws never breaks the session", async () => {
  const bad = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } };
  const { s, posts } = setup({ storage: bad });
  await s.start();
  await s.submit("c1", "pipeline", "ok", "");
  assert.equal(posts.length, 1);
});
