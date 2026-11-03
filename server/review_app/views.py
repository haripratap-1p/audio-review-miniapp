import time
from typing import Any

from .config import MAX_LINES, SYSTEMS
from .results import avail
from .store import db

_writes: dict = {}  # user_id -> recent write timestamps


def light(i: dict, systems: tuple = SYSTEMS) -> dict:
    # list row: no transcripts, only my own votes, only the systems this user may see
    av = avail(i)
    return {
        "id": i["id"],
        "store": i["store"],
        "kind": i["kind"],
        "who": i["who"],
        "date": i["date"],
        "time": i["time"],
        "arrived": i["arrived"],
        "duration": i["duration"],
        "avail": {s: av[s] for s in systems},
        "na": [s for s in i["na"] if s in systems],
        "ready": av["gemma"] and "gemma" in systems,
        "mine": {s: i["votes"][s]["mine"] for s in systems},
        "team": {s: i["votes"][s]["result"] if i["votes"][s]["mine"] else None for s in systems},
    }


def detail(i: dict, systems: tuple = SYSTEMS) -> dict:
    # team votes and notes stay hidden until this user has voted on that system (no copying)
    votes = {
        s: (v if v["mine"] else {**v, "ok": None, "bad": None, "result": None, "notes": []})
        for s, v in i["votes"].items()
        if s in systems
    }
    out = {k: v for k, v in i.items() if k not in ("_js", "votes", "sort") and k not in set(SYSTEMS) - set(systems)}
    out["na"] = [s for s in i["na"] if s in systems]
    return {**out, "votes": votes}


def overview(items: list, rows: list, uid: int, today: str, systems: tuple = SYSTEMS) -> dict:
    ready = [i for i in items if i["gemma"] and not i["gemma"]["error"]]
    return {
        "total": len(items),
        "ready": len(ready),
        "team_pipeline": sum(bool(i["votes"]["pipeline"]["result"]) for i in items),
        "team_done": sum(all(i["votes"][s]["result"] for s in systems if avail(i)[s]) for i in items),
        "my_today": len({r["conv"] for r in rows if r["user_id"] == uid and r["ts"][:10] == today}),
    }


def line_info(cid: str, uid: int, systems: tuple, mine_overall: dict, team: bool) -> dict:
    # my marks per line; team counts only in the full view and only after I've voted on that system
    with db() as c:
        rows = c.execute(
            "SELECT system, line, user_id, verdict, note FROM line_reviews WHERE conv=?", (cid,)
        ).fetchall()
    out = {}
    for s in systems:
        mine = {str(ln): {"verdict": v, "note": n} for sy, ln, u, v, n in rows if sy == s and u == uid}
        counts: dict = {}
        if team and mine_overall.get(s):
            for sy, ln, _, v, _ in rows:
                if sy == s:
                    counts.setdefault(str(ln), {"ok": 0, "bad": 0})[v] += 1
        out[s] = {"mine": mine, "team": counts}
    return out


def clean_lines(raw: Any, n_turns: int) -> dict | None:
    # {"<line idx>": {"verdict": "ok"|"bad", "note": str}} -> {idx: (verdict, note)}; None if anything is off
    if raw is None:
        return {}
    if not isinstance(raw, dict) or len(raw) > MAX_LINES:
        return None
    out = {}
    for k, v in raw.items():
        if not (isinstance(k, str) and k.isdigit() and int(k) < n_turns and isinstance(v, dict)):
            return None
        if v.get("verdict") not in ("ok", "bad") or not isinstance(v.get("note", ""), str):
            return None
        out[int(k)] = (v["verdict"], v.get("note", "")[:200])
    return out


def rate_ok(uid: int, limit: int = 60, window: int = 60) -> bool:
    now = time.time()
    recent = [t for t in _writes.get(uid, []) if now - t < window]
    _writes[uid] = recent + [now]
    return len(recent) < limit
