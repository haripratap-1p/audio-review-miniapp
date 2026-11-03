import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .config import IST, STEM, SYSTEMS, get_settings

_cache: dict = {}  # path -> (mtime, parsed json)


def conv_id(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def pipeline_turns(convo: str) -> list:
    turns = []
    for line in convo.splitlines():
        m = re.match(r"\[Speaker_(\d+)\]:\s*(.*)", line.strip())
        if m:
            turns.append({"speaker": f"Speaker {int(m[1])}", "text": m[2]})
        elif line.strip() and turns:
            turns[-1]["text"] += " " + line.strip()
    return turns


def verdict(votes: list) -> str | None:
    # majority of reviewers; a tie goes to the latest vote
    if not votes:
        return None
    ok = sum(v["verdict"] == "ok" for v in votes)
    bad = len(votes) - ok
    return "ok" if ok > bad else "bad" if bad > ok else max(votes, key=lambda v: v["ts"])["verdict"]


def load(p: Path) -> dict | None:
    # results never change in place often; re-parse only when the file's mtime moves
    try:
        mt = p.stat().st_mtime
    except FileNotFoundError:
        return None
    hit = _cache.get(p)
    if not hit or hit[0] != mt:
        hit = _cache[p] = (mt, json.loads(p.read_text(encoding="utf-8")))
    return hit[1]


def model_result(g: dict | None) -> dict | None:
    if g is None or g.get("skipped"):
        return None
    return {
        "sentiment": g.get("sentiment", ""),
        "summary": g.get("summary", ""),
        "turns": g.get("turns", []),
        "secs": g.get("secs"),
        "error": g.get("error", ""),
        "model": g.get("model", ""),
    }


def avail(i: dict) -> dict:
    return {s: bool(i[s] and not i[s].get("error")) for s in SYSTEMS}


def collect(rows: list, uid: int | None = None) -> list:
    st = get_settings()
    by_conv: dict = {}
    for r in rows:
        by_conv.setdefault((r["conv"], r["system"]), []).append(r)
    items = []
    for js in st.results.glob("*/*/*.json"):
        if "." in js.stem:  # model outputs are <stem>.<model>.json
            continue
        m = STEM.match(js.stem)
        if not m or js.parent.name < st.post_from:  # folder = day it reached us; file name = phone's call time
            continue
        d = load(js)
        if not d or not (d.get("conversation") or "").strip():
            continue  # silence: nothing to review
        key = f"{js.parent.parent.name}/{js.stem}"
        cid = conv_id(key)
        votes = {}
        for s in SYSTEMS:
            vs = by_conv.get((cid, s), [])
            votes[s] = {
                "ok": sum(v["verdict"] == "ok" for v in vs),
                "bad": sum(v["verdict"] == "bad" for v in vs),
                "result": verdict(vs),
                "mine": next((v["verdict"] for v in vs if v["user_id"] == uid), None),
                "my_note": next((v["note"] for v in vs if v["user_id"] == uid), ""),
                "notes": [f"{v['user_name']}: {v['note']}" for v in vs if v["note"]],
            }
        models = {s: load(js.with_name(f"{js.stem}.{s}.json")) for s in SYSTEMS[1:]}
        items.append(
            {
                "id": cid,
                "key": key,
                "store": js.parent.parent.name,
                "kind": "call" if m[1] else "in-store",
                "who": (m[1] or "In-store").replace("_", " ").strip(),
                "date": f"{m[2]}-{m[3]}-{m[4]}",
                "time": f"{m[5]}:{m[6]}",
                "sort": "".join(m.groups()[1:]),
                "duration": d.get("duration", ""),
                "pipeline": {
                    "sentiment": d.get("sentiment", ""),
                    "summary": d.get("summary", ""),
                    "turns": pipeline_turns(d["conversation"]),
                },
                **{s: model_result(g) for s, g in models.items()},
                "na": [s for s, g in models.items() if (g or {}).get("skipped") == "language not supported"],
                "arrived": arrived(js),
                "votes": votes,
                "_js": js,
            }
        )
    return sorted(items, key=lambda i: (i["arrived"], i["sort"]), reverse=True)


def arrived(js: Path) -> str:
    # when the recording reached the pipeline: its audio file's mtime, else the result file's
    audio = next(js.parent.joinpath("audio").glob(js.stem + ".*"), None)
    try:
        t = (audio or js).stat().st_mtime
    except FileNotFoundError:
        t = 0
    return datetime.fromtimestamp(t, IST).isoformat(timespec="seconds")
