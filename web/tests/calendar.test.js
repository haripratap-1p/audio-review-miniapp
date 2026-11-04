// date filter: month grid (Monday first) and the day + tab filter
import { test } from "node:test";
import assert from "node:assert/strict";
import { monthGrid, monthLabel } from "../js/format.js?v=__V__";

test("monthGrid starts on Monday and has every day", () => {
  const nov = monthGrid("2026-11");  // 1 Nov 2026 is a Sunday
  assert.equal(nov.filter((d) => d === null).length, 6);
  assert.equal(nov[6], "2026-11-01");
  assert.equal(nov.at(-1), "2026-11-30");
  assert.equal(monthGrid("2028-02").filter(Boolean).length, 29);
  assert.equal(monthGrid("2027-02").filter(Boolean).length, 28);
  assert.equal(monthGrid("2027-02")[0], "2027-02-01");  // 1 Feb 2027 is a Monday: no blanks
  assert.equal(monthLabel("2026-11"), "November 2026");
});

test("inView filters by tab and arrival day", async () => {
  globalThis.window = {};
  const { state, inView, queue } = await import("../js/state.js?v=__V__");
  const call3 = { id: "a", kind: "call", arrived: "2026-11-03T10:00:00+05:30", mine: {} };
  const call4 = { id: "b", kind: "call", arrived: "2026-11-04T10:00:00+05:30", mine: {} };
  const shop4 = { id: "c", kind: "in-store", arrived: "2026-11-04T11:00:00+05:30", mine: {} };
  Object.assign(state, { items: [call3, call4, shop4], kind: "call", day: null });
  assert.deepEqual(state.items.filter(inView).map((i) => i.id), ["a", "b"]);
  state.day = "2026-11-04";
  assert.deepEqual(state.items.filter(inView).map((i) => i.id), ["b"]);
  assert.deepEqual(queue().map((i) => i.id), ["b"]);
  state.kind = "in-store";
  assert.deepEqual(state.items.filter(inView).map((i) => i.id), ["c"]);
});
