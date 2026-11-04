// one reviewer's session: line-mark drafts, the vote queue (saved across reopen), optimistic state and undo
const key = (id, system) => `${id}|${system}`;
const EMPTY = Object.freeze({});

// deps: { fetch, base, initData, storage, tg, userId, state: {items, details, myToday}, wait(ms), retryMs }
export function createSession({ fetch, base = "", initData = "", storage = null, tg = null, userId = "", state, wait, retryMs = 5000 }) {
  const drafts = new Map(), saved = new Map(), listeners = [];
  const storeKey = `pendingVotes:${userId}`;
  let queue = [], loaded = false, busy = false;
  wait = wait || ((ms) => new Promise((r) => setTimeout(r, ms)));

  const emit = (event) => listeners.forEach((fn) => fn(event));
  const persist = () => {
    try { queue.length ? storage.setItem(storeKey, JSON.stringify(queue)) : storage.removeItem(storeKey); } catch {}
  };
  const restore = () => {
    try {
      const list = JSON.parse(storage.getItem(storeKey) || "[]");
      return Array.isArray(list) ? list.filter((v) => v && v.id && v.system && v.verdict) : [];
    } catch { return []; }
  };
  const changed = () => {
    if (tg) {
      if (queue.length || drafts.size) tg.enableClosingConfirmation && tg.enableClosingConfirmation();
      else tg.disableClosingConfirmation && tg.disableClosingConfirmation();
    }
    emit({});
  };

  // optimistic: row.mine, my line marks and today's count follow the vote before the server answers
  function apply({ id, system, verdict, lines }) {
    const row = state.items.find((i) => i.id === id);
    if (row) {
      const before = Object.values(row.mine).some(Boolean);
      row.mine[system] = verdict === "clear" ? null : verdict;
      const after = Object.values(row.mine).some(Boolean);
      if (after && !before) state.myToday = (state.myToday || 0) + 1;
      if (before && !after) state.myToday = Math.max(0, (state.myToday || 0) - 1);
    }
    saved.set(key(id, system), verdict === "clear" ? {} : { ...(lines || {}) });
  }

  function enqueue(vote) {
    apply(vote);
    queue.push(vote);
    persist();
    changed();
    return flush();
  }

  async function flush() {
    if (busy) return;
    busy = true;
    try {
      while (queue.length) {
        const v = queue[0];
        let status = 0, error = "";
        try {
          const r = await fetch(`${base}/api/review`, { method: "POST", headers: { "X-Init-Data": initData, "Content-Type": "application/json" }, body: JSON.stringify(v) });
          status = r.status;
          if (!r.ok) error = (await r.json().catch(() => ({}))).error || "";
        } catch {}
        if (status >= 200 && status < 300) {
          queue.shift();
          if (state.details) state.details.delete(v.id);
        } else if (status === 401 || status === 403) {
          return emit({ expired: queue.length });
        } else if (status === 400 || status === 409) {
          queue.shift();
          if (v.verdict !== "clear") apply({ ...v, verdict: "clear" });
          emit({ toast: status === 409 ? error || "This result isn't ready" : `Couldn't save this review: ${error || "invalid"}` });
        } else {
          emit({ toast: "Couldn't save yet, retrying…" });
          await wait(retryMs);
          continue;
        }
        persist();
        changed();
      }
    } finally {
      busy = false;
    }
  }

  return {
    // verdict null removes the mark; marks stay drafts until submit
    mark(id, system, line, verdict, note = "") {
      const k = key(id, system), m = { ...(drafts.get(k) || {}) };
      if (verdict) m[line] = { verdict, note }; else delete m[line];
      Object.keys(m).length ? drafts.set(k, m) : drafts.delete(k);
      changed();
    },
    draft: (id, system) => drafts.get(key(id, system)) || EMPTY,
    // my marks (optimistic if I voted this session) and the team's counts from the loaded detail
    lines(id, system, detail) {
      const info = (detail && detail.lines && detail.lines[system]) || {};
      const k = key(id, system);
      return { mine: saved.has(k) ? saved.get(k) : info.mine || {}, team: info.team || {} };
    },
    submit(id, system, verdict, note = "") {
      const lines = { ...(drafts.get(key(id, system)) || {}) };
      drafts.delete(key(id, system));
      return enqueue({ id, system, verdict, note, lines });
    },
    undo(id, system) {
      drafts.delete(key(id, system));
      return enqueue({ id, system, verdict: "clear", note: "" });
    },
    pending: () => queue.length,
    onChange(fn) { listeners.push(fn); },
    // after each list load: pick up votes left from a closed or expired session, re-apply them and send
    start() {
      if (!loaded) { loaded = true; queue = [...restore(), ...queue]; }
      queue.forEach(apply);
      changed();
      return flush();
    },
  };
}
