// review screens: phone queue one result at a time, PC desk with results side by side
import { state, SYSTEMS, LABEL, has, isDone, nextOpen, notUsed, missingText, queue } from "./state.js?v=__V__";
import { $app, h, icon, badge, haptic, toast, skeleton, showError, confirmSheet, reasonSheet } from "./dom.js?v=__V__";
import { verdictText, whenText } from "./format.js?v=__V__";
import { getDetail, prefetch, saveVote, draftOf, guardClose } from "./api.js?v=__V__";
import { player } from "./player.js?v=__V__";
import { topbar, sidebarList } from "./list.js?v=__V__";
import { go } from "./router.js?v=__V__";

// lines: { marks: {idx: {verdict, note}}, team: {idx: {ok, bad}}, edit: bool, onMark(idx, verdict|null, note) }
function transcript(result, pending, lines) {
  if (!result) return h("p", { class: "note" }, pending);
  if (result.error) return h("p", { class: "warn" }, "This result failed: " + result.error);
  const num = (s) => (String(s || "?").match(/\d+/) || ["?"])[0];
  const marksFor = (k) => {
    if (!lines) return null;
    const m = lines.marks[k], t = lines.team && lines.team[k];
    const team = t ? h("span", { class: "note" }, `Team ✓${t.ok} ✗${t.bad}`) : null;
    if (!lines.edit) return h("div", { class: "lmarks" }, m ? badge(m.verdict, m.verdict === "ok" ? "Line correct" : "Line wrong") : null, team);
    const pick = (v) => () => {
      if (m && m.verdict === v) return lines.onMark(k, null, "");
      if (v === "ok") return lines.onMark(k, "ok", "");
      reasonSheet((note) => lines.onMark(k, "bad", note), `What was wrong in line ${Number(k) + 1}?`, "Mark line wrong");
    };
    return h("div", { class: "lmarks" },
      h("button", { class: "lm ok", "aria-pressed": String(m?.verdict === "ok"), "aria-label": `Line ${Number(k) + 1} is correct`, onclick: pick("ok") }, icon("check")),
      h("button", { class: "lm bad", "aria-pressed": String(m?.verdict === "bad"), "aria-label": `Line ${Number(k) + 1} is wrong`, onclick: pick("bad") }, icon("cross")), team);
  };
  return h("div", {},
    h("p", { class: "summary" }, h("span", { class: "mood" }, result.sentiment || "No mood"), result.summary ? ` ${result.summary}` : ""),
    h("ol", { class: `turns${lines ? " marked" : ""}` }, (result.turns || []).map((t, k) => h("li", { class: lines?.marks[k] ? `is-${lines.marks[k].verdict}` : "" },
      h("span", { class: "spk", title: t.speaker || "" }, num(t.speaker)),
      h("div", {},
        h("p", { class: "said" }, t.text || ""),
        t.english && t.english !== t.text ? h("p", { class: "en" }, t.english) : null,
        t.sentiment ? h("p", { class: "tone" }, t.sentiment) : null,
        lines?.marks[k]?.note ? h("p", { class: "lnote" }, `Wrong: ${lines.marks[k].note}`) : null),
      marksFor(String(k))))));
}

// one system's review: transcript with line marks, then Correct/Wrong behind a confirm, or my saved review with Undo
function reviewArea(row, d, sys, after) {
  const result = d[sys], saved = row.mine[sys], n = (result?.turns || []).length;
  const info = (d.lines && d.lines[sys]) || { mine: {}, team: {} };
  if (!has(row, sys)) return { ask: "Nothing to check yet", body: transcript(null, missingText(row, sys)), actions: null };
  if (saved) {
    const undo = () => confirmSheet("Undo your review?",
      [`Your “${verdictText(saved)}” for ${LABEL[sys]} on ${row.who} and your line marks will be removed.`, "It goes back to To review."],
      "Undo my review", "bad solid", () => {
        saveVote(row.id, sys, "clear");
        if (d.lines) d.lines[sys] = { mine: {}, team: {} };
        haptic("warning");
        toast("Review removed");
        after("undo");
      });
    return {
      ask: `You reviewed ${LABEL[sys]}`,
      body: transcript(result, "", { marks: info.mine, team: info.team, edit: false }),
      actions: h("div", { class: "row saved" }, badge(saved, `You said ${verdictText(saved)}`), h("button", { class: "btn quiet", onclick: undo }, "Undo my review")),
    };
  }
  const draft = draftOf(row.id, sys);
  const body = h("div", {});
  const counter = h("p", { class: "note counter", "aria-live": "polite" });
  const paintBody = () => {
    const vals = Object.values(draft), ok = vals.filter((m) => m.verdict === "ok").length;
    counter.textContent = vals.length ? `${vals.length} of ${n} lines marked: ${ok} correct, ${vals.length - ok} wrong. Saved only when you submit.`
      : "Optional: mark each line ✓ or ✗, then choose Correct or Wrong for the whole result.";
    body.replaceChildren(transcript(result, "", {
      marks: draft, edit: true,
      onMark: (k, v, note) => { v ? (draft[k] = { verdict: v, note }) : delete draft[k]; guardClose(); paintBody(); },
    }));
  };
  const submit = (v, note) => {
    const vals = Object.values(draft), bad = vals.filter((m) => m.verdict === "bad").length, good = vals.length - bad;
    const lines = [
      `${LABEL[sys]} · ${row.who}`,
      h("span", {}, "Whole result: ", badge(v, verdictText(v)), note ? ` (${note})` : ""),
      `Lines: ${good} correct · ${bad} wrong · ${n - vals.length} not marked`,
      v === "ok" && bad ? { warn: true, text: `You marked ${bad} line${bad === 1 ? "" : "s"} wrong but the whole result Correct. Check before submitting.` } : null,
      v === "bad" && vals.length && !bad ? { warn: true, text: "Every marked line is correct but the whole result is Wrong. Check before submitting." } : null,
    ];
    confirmSheet("Submit this review?", lines, "Submit review", v === "ok" ? "ok solid" : "bad solid", () => {
      saveVote(row.id, sys, v, note, { ...draft });
      if (d.lines) d.lines[sys] = { mine: { ...draft }, team: {} };
      state.drafts.delete(`${row.id}|${sys}`);
      guardClose();
      haptic(v === "ok" ? "success" : "warning");
      after(v);
    });
  };
  paintBody();
  return {
    ask: `Is the ${LABEL[sys]} result correct?`,
    body: h("div", {}, counter, body),
    actions: h("div", { class: "row" },
      h("button", { class: "btn bad", onclick: () => reasonSheet((note) => submit("bad", note)) }, icon("cross"), "Wrong"),
      h("button", { class: "btn ok solid", onclick: () => submit("ok", "") }, icon("check"), "Correct")),
  };
}

export async function renderReview(id) {
  const q = queue();
  const row = state.items.find((i) => i.id === id) || q[0];
  if (!row) return go("done");
  state.kind = row.kind;
  state.current = row.id;
  $app.replaceChildren(topbar("queue"), skeleton());
  let d;
  try {
    d = await getDetail(row.id);
  } catch (e) {
    return showError(e, () => go("review", row.id));
  }
  prefetch(q.find((i) => i.id !== row.id)?.id);
  let cur = nextOpen(row) || "pipeline";
  const audio = player(row.id);
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const panel = h("section", { class: "panel", role: "tabpanel" });
  const verdict = h("div", { class: "verdict" });
  const done = [];

  const paint = () => {
    const notReady = !has(row, cur);
    tabs.replaceChildren(...SYSTEMS.map((s) => h("button", {
      class: "tab", role: "tab", "aria-selected": String(s === cur), onclick: () => { cur = s; paint(); },
    }, LABEL[s], row.mine[s] ? badge(row.mine[s], verdictText(row.mine[s])) : null)));
    const ra = reviewArea(row, d, cur, (v) => (v === "undo" ? paint() : vote()));
    panel.replaceChildren(notReady ? transcript(null, notUsed(row, cur) ? missingText(row, cur) : `${missingText(row, cur)} It will come back to your queue when it is.`) : ra.body);
    verdict.replaceChildren(
      h("div", { class: "row between" }, h("p", { class: "ask" }, ra.ask), h("button", { class: "link", onclick: skip }, "Skip")),
      ra.actions);
    window.scrollTo({ top: 0, behavior: "instant" });
  };

  const vote = () => {
    done.push(cur);
    const nextSys = nextOpen(row, cur);
    if (nextSys) { cur = nextSys; return paint(); }
    state.myToday += 1;
    go("next");
    toast("Saved", { label: "Undo", run: () => { done.forEach((s) => saveVote(row.id, s, "clear")); go("review", row.id); } });
  };

  const skip = () => {
    state.skipped = [...state.skipped.filter((x) => x !== row.id), row.id];
    try { sessionStorage.setItem("skipped", JSON.stringify(state.skipped)); } catch {}
    const next = queue().find((i) => i.id !== row.id);
    next ? go("review", next.id) : go("done");
  };

  $app.replaceChildren(topbar("queue"),
    h("section", { class: "who" },
      h("div", { class: "row between" }, h("h2", {}, row.who), h("span", { class: "kind" }, row.kind === "call" ? "Call" : "In-store")),
      h("p", { class: "meta" }, h("span", {}, row.store), h("span", {}, whenText(row)), row.duration ? h("span", {}, row.duration) : null)),
    audio, tabs, panel, verdict);
  paint();
}

export function renderDone() {
  $app.replaceChildren(topbar("queue"), h("section", { class: "message" },
    h("h1", {}, "You're up to date"),
    h("p", {}, state.myToday ? `You've checked ${state.myToday} conversation${state.myToday === 1 ? "" : "s"} today.` : "Nothing is waiting for you right now."),
    h("p", { class: "note" }, "New conversations appear here as they're processed."),
    h("button", { class: "btn primary", onclick: () => go("refresh") }, "Refresh"),
    h("button", { class: "link", onclick: () => go("list") }, "See all conversations")));
}

// PC / laptop: list on the left, both results side by side
export async function renderDesk(id) {
  const row = state.items.find((i) => i.id === id) || queue()[0] || state.items.find((i) => i.kind === state.kind);
  if (row) state.kind = row.kind;
  state.current = row?.id;
  const main = h("div", { class: "desk-main" });
  $app.replaceChildren(h("div", { class: "desk" }, sidebarList(row?.id), main));
  if (!row) return main.replaceChildren(h("section", { class: "message" }, h("h1", {}, "You're up to date"),
    h("p", { class: "note" }, "New conversations appear here as they're processed."), h("button", { class: "btn primary", onclick: () => go("refresh") }, "Refresh")));
  main.replaceChildren(skeleton());
  let d;
  try {
    d = await getDetail(row.id);
  } catch (e) {
    return showError(e, () => go("review", row.id));
  }
  if (state.current !== row.id) return;  // user clicked another row meanwhile
  prefetch(queue().find((i) => i.id !== row.id)?.id);
  const audio = player(row.id);
  const done = [];
  const column = (sys) => {
    const ra = reviewArea(row, d, sys, (v) => (v === "undo" ? paint() : vote(sys)));
    return h("section", { class: "col" },
      h("div", { class: "row between col-head" }, h("h2", {}, LABEL[sys]), row.mine[sys] ? badge(row.mine[sys], verdictText(row.mine[sys])) : null),
      h("div", { class: "col-body" }, ra.body),
      ra.actions ? h("div", { class: "col-verdict" }, ra.actions) : null);
  };
  const cols = h("div", { class: "cols" });
  const paint = () => cols.replaceChildren(...SYSTEMS.map(column));
  const vote = (sys) => {
    done.push(sys);
    if (!isDone(row)) return paint();
    state.myToday += 1;
    go("review", queue()[0]?.id || row.id);
    toast("Saved", { label: "Undo", run: () => { done.forEach((s) => saveVote(row.id, s, "clear")); go("review", row.id); } });
  };
  paint();
  main.replaceChildren(
    h("section", { class: "who" },
      h("div", { class: "row between" }, h("h2", {}, row.who), h("span", { class: "kind" }, row.kind === "call" ? "Call" : "In-store")),
      h("p", { class: "meta" }, h("span", {}, row.store), h("span", {}, whenText(row)), row.duration ? h("span", {}, row.duration) : null)),
    audio, cols);
}
