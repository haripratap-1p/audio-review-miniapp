import hashlib
import json
import os
import re
import sqlite3
import subprocess
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import IST, LABELS, MAX_LINES, REFERENCE, SCORED, STEM, SYSTEMS, get_settings
from .store import all_rows, db, judged
from .viewer import Viewer

_extract = threading.Lock()


class Rejected(Exception):
    status = 400


class NotAllowed(Rejected):
    status = 403


class NotReady(Rejected):
    status = 409


@dataclass(frozen=True)
class Conversation:
    id: str
    key: str
    store: str
    kind: str
    who: str
    date: str
    time: str
    sort: str
    duration: str
    admin_id: str
    arrived: str
    js: Path
    audio: Path | None
    results: dict  # system -> result or None
    na: list
    reviews: dict  # system -> review rows

    def available(self, s: str) -> bool:
        r = self.results[s]
        return bool(r and not r.get("error"))

    def verdict(self, s: str) -> str | None:
        return majority(self.reviews[s])

    def scored(self, s: str) -> str | None:
        # the pipeline is scored on analysis votes only; Tech team votes don't count
        vs = self.reviews[s]
        return majority([v for v in vs if v.get("source") in (None, "analysis")] if s == "pipeline" else vs)


def conv_id(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def source_audio(js: Path) -> Path | None:
    return next(js.parent.joinpath("audio").glob(js.stem + ".*"), None)


def majority(votes: list) -> str | None:
    # majority of reviewers; a tie goes to the latest vote
    if not votes:
        return None
    ok = sum(v["verdict"] == "ok" for v in votes)
    bad = len(votes) - ok
    return "ok" if ok > bad else "bad" if bad > ok else max(votes, key=lambda v: v["ts"])["verdict"]


def pipeline_turns(convo: str) -> list:
    turns = []
    for line in convo.splitlines():
        m = re.match(r"\[Speaker_(\d+)\]:\s*(.*)", line.strip())
        if m:
            turns.append({"speaker": f"Speaker {int(m[1])}", "text": m[2]})
        elif line.strip() and turns:
            turns[-1]["text"] += " " + line.strip()
    return turns


def _load(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _model_result(g: dict | None) -> dict | None:
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


def _arrived(js: Path, audio: Path | None) -> str:
    # when the recording reached the pipeline: its audio file's mtime, else the result file's
    try:
        t = (audio or js).stat().st_mtime
    except FileNotFoundError:
        t = 0
    return datetime.fromtimestamp(t, IST).isoformat(timespec="seconds")


def kind_of(stem: str) -> str:
    m = STEM.match(stem)
    return "call" if m and m[1] else "in-store"


def _posted() -> set:
    f = get_settings().posted_file
    return set(json.loads(f.read_text())) if f.exists() else set()


_scan_lock = threading.Lock()
_cache: dict = {}  # key -> (fingerprint + settings), convs -> list, by_id -> {id: Conversation}


def _fingerprint(results: Path) -> frozenset:
    # every result and audio file's (path, mtime, size): any new, rewritten or touched file changes it
    out = []
    for day in results.glob("*/*"):
        for d in (day, day / "audio"):
            try:
                with os.scandir(d) as it:
                    out += [(e.path, s.st_mtime_ns, s.st_size) for e in it if e.is_file() for s in [e.stat()]]
            except (FileNotFoundError, NotADirectoryError):
                pass
    return frozenset(out)


def _audio_files(d: Path) -> dict:
    # one listing per day folder instead of a glob per conversation
    out: dict = {}
    try:
        for name in sorted(os.listdir(d)):
            out.setdefault(name.split(".", 1)[0], d / name)
    except FileNotFoundError:
        pass
    return out


def _files() -> tuple[list, dict]:
    # result files parsed once and reused until a file under live_results changes; reviews are attached per call
    st = get_settings()
    posted = frozenset() if st.calls_on and st.instore_on else frozenset(_posted())
    key = (st.results, st.post_from, st.calls_on, st.instore_on, posted, _fingerprint(st.results))
    with _scan_lock:
        if _cache.get("key") != key:
            convs = _read(st, posted)
            _cache.update(key=key, convs=convs, by_id={c.id: c for c in convs})
        return _cache["convs"], _cache["by_id"]


def _with_reviews(c: Conversation, rows: list) -> Conversation:
    return replace(c, reviews={s: [r for r in rows if r["system"] == s] for s in SYSTEMS})


def scan(rows: list | None = None) -> list[Conversation]:
    # newest arrival first; rows default to every review in the db
    by_conv: dict = {}
    for r in all_rows() if rows is None else rows:
        by_conv.setdefault(r["conv"], []).append(r)
    return [_with_reviews(c, by_conv.get(c.id, [])) for c in _files()[0]]


def _read(st: Any, posted: frozenset) -> list[Conversation]:
    out = []
    audio_dirs: dict = {}
    for js in st.results.glob("*/*/*.json"):
        if "." in js.stem:  # model outputs are <stem>.<model>.json
            continue
        m = STEM.match(js.stem)
        if not m or js.parent.name < st.post_from:  # folder = day it reached us; file name = phone's call time
            continue
        key, kind = f"{js.parent.parent.name}/{js.stem}", kind_of(js.stem)
        if not st.kind_on(kind) and key not in posted:
            continue  # switched off: show only what already reached the group
        d = _load(js)
        if not d or not (d.get("conversation") or "").strip():
            continue  # silence: nothing to review
        cid = conv_id(key)
        models = {s: _load(js.with_name(f"{js.stem}.{s}.json")) for s in SYSTEMS[1:]}
        pipeline = {"sentiment": d.get("sentiment", ""), "summary": d.get("summary", "")}
        if js.parent not in audio_dirs:
            audio_dirs[js.parent] = _audio_files(js.parent / "audio")
        audio = audio_dirs[js.parent].get(js.stem)
        out.append(
            Conversation(
                id=cid,
                key=key,
                store=js.parent.parent.name,
                kind=kind,
                who=(m[1] or "In-store").replace("_", " ").strip(),
                date=f"{m[2]}-{m[3]}-{m[4]}",
                time=f"{m[5]}:{m[6]}",
                sort="".join(m.groups()[1:]),
                duration=d.get("duration", ""),
                admin_id=d.get("adminId", ""),
                arrived=_arrived(js, audio),
                js=js,
                audio=audio,
                results={
                    "pipeline": {**pipeline, "turns": pipeline_turns(d["conversation"])},
                    **{s: _model_result(g) for s, g in models.items()},
                },
                na=[s for s, g in models.items() if (g or {}).get("skipped") == "language not supported"],
                reviews={s: [] for s in SYSTEMS},
            )
        )
    return sorted(out, key=lambda c: (c.arrived, c.sort), reverse=True)


def _find(cid: str, rows: list | None = None) -> Conversation | None:
    c = _files()[1].get(cid)
    if not c:
        return None
    return _with_reviews(c, [r for r in (all_rows() if rows is None else rows) if r["conv"] == cid])


def _tally(vs: list, uid: int) -> dict:
    return {
        "ok": sum(v["verdict"] == "ok" for v in vs),
        "bad": sum(v["verdict"] == "bad" for v in vs),
        "result": majority(vs),
        "mine": next((v["verdict"] for v in vs if v["user_id"] == uid), None),
        "my_note": next((v["note"] for v in vs if v["user_id"] == uid), ""),
        "notes": [f"{v['user_name']}: {v['note']}" for v in vs if v["note"]],
    }


def _row(c: Conversation, v: Viewer) -> dict:
    # list row: no transcripts, only my own votes, only the systems this viewer may see
    t = {s: _tally(c.reviews[s], v.uid) for s in v.systems}
    return {
        "id": c.id,
        "store": c.store,
        "kind": c.kind,
        "who": c.who,
        "date": c.date,
        "time": c.time,
        "arrived": c.arrived,
        "duration": c.duration,
        "avail": {s: c.available(s) for s in v.systems},
        "na": [s for s in c.na if s in v.systems],
        "ready": c.available("gemma") and "gemma" in v.systems,
        "mine": {s: t[s]["mine"] for s in v.systems},
        "team": {s: t[s]["result"] if t[s]["mine"] else None for s in v.systems},
    }


def _votes(c: Conversation, v: Viewer) -> dict:
    # team votes and notes stay hidden until this viewer has voted on that system (no copying)
    t = {s: _tally(c.reviews[s], v.uid) for s in v.systems}
    return {s: x if x["mine"] else {**x, "ok": None, "bad": None, "result": None, "notes": []} for s, x in t.items()}


def _lines(c: Conversation, v: Viewer) -> dict:
    # my marks per line; team counts only in the full view and only after I've voted on that system
    with db() as conn:
        rows = conn.execute(
            "SELECT system, line, user_id, verdict, note FROM line_reviews WHERE conv=?", (c.id,)
        ).fetchall()
    out = {}
    for s in v.systems:
        mine = {str(ln): {"verdict": vd, "note": n} for sy, ln, u, vd, n in rows if sy == s and u == v.uid}
        counts: dict = {}
        if v.full and _tally(c.reviews[s], v.uid)["mine"]:
            for sy, ln, _, vd, _ in rows:
                if sy == s:
                    counts.setdefault(str(ln), {"ok": 0, "bad": 0})[vd] += 1
        out[s] = {"mine": mine, "team": counts}
    return out


def listing(v: Viewer, today: str | None = None) -> dict:
    today = today or datetime.now(IST).strftime("%Y-%m-%d")
    rows = all_rows()
    convs = scan(rows)
    return {
        "items": [_row(c, v) for c in convs],
        "total": len(convs),
        "ready": sum(c.available("gemma") for c in convs),
        "team_pipeline": sum(bool(c.verdict("pipeline")) for c in convs),
        "team_done": sum(all(c.verdict(s) for s in v.systems if c.available(s)) for c in convs),
        "my_today": len({r["conv"] for r in rows if r["user_id"] == v.uid and r["ts"][:10] == today}),
    }


def get(cid: str, v: Viewer) -> dict | None:
    c = _find(cid)
    if not c:
        return None
    return {
        "id": c.id,
        "key": c.key,
        "store": c.store,
        "kind": c.kind,
        "who": c.who,
        "date": c.date,
        "time": c.time,
        "duration": c.duration,
        **{s: c.results[s] for s in SYSTEMS if s in v.systems},
        "na": [s for s in c.na if s in v.systems],
        "arrived": c.arrived,
        "votes": _votes(c, v),
        "lines": _lines(c, v),
        **(_reference(c) if v.full else {}),
    }


def _reference(c: Conversation) -> dict:
    # full view only: the Gemini reference transcript and the AI judge's verdict per scored system
    ref = c.results[REFERENCE]
    return {
        "reference": {**ref, "label": LABELS[REFERENCE]} if ref else None,
        "judge": {s: j for (_, s), j in judged(c.id).items() if s in SCORED},
    }


def _marks(raw: Any, n_turns: int) -> dict | None:
    # {"<line idx>": {"verdict": "ok"|"bad", "note": str}} -> {idx: (verdict, note)}; None if anything is off
    if raw is None:
        return {}
    if not isinstance(raw, dict) or len(raw) > MAX_LINES:
        return None
    out = {}
    for k, x in raw.items():
        if not (isinstance(k, str) and k.isdigit() and int(k) < n_turns and isinstance(x, dict)):
            return None
        if x.get("verdict") not in ("ok", "bad") or not isinstance(x.get("note", ""), str):
            return None
        out[int(k)] = (x["verdict"], x.get("note", "")[:200])
    return out


def vote(v: Viewer, cid: str, system: Any, verdict: Any, note: Any = "", lines: Any = None) -> dict:
    # one submit replaces my whole review of this system: overall verdict plus every line mark; "clear" undoes it
    c = _find(cid, rows=[])
    if system not in SCORED or verdict not in ("ok", "bad", "clear") or not c:
        raise Rejected("bad request")
    if system not in v.systems:
        raise NotAllowed("not allowed")
    if verdict != "clear" and not c.available(system):
        raise NotReady("This result isn't ready")
    marks = _marks(lines, len((c.results[system] or {}).get("turns") or []))
    if marks is None:
        raise Rejected("bad line marks")
    now = datetime.now(IST).isoformat()
    with db() as conn:
        conn.execute("DELETE FROM line_reviews WHERE conv=? AND system=? AND user_id=?", (cid, system, v.uid))
        if verdict == "clear":
            conn.execute("DELETE FROM reviews WHERE conv=? AND system=? AND user_id=?", (cid, system, v.uid))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO reviews (conv, system, user_id, user_name, verdict, note, ts, source) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (cid, system, v.uid, v.name, verdict, str(note)[:500], now, "team" if v.full else "analysis"),
            )
            conn.executemany(
                "INSERT INTO line_reviews VALUES (?,?,?,?,?,?,?,?)",
                [(cid, system, ln, v.uid, v.name, lv, ln_note, now) for ln, (lv, ln_note) in marks.items()],
            )
    with db() as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM reviews WHERE conv=?", (cid,))]
    c = replace(c, reviews={s: [r for r in rows if r["system"] == s] for s in SYSTEMS})
    return {"votes": _votes(c, v), "lines": _lines(c, v)}


def audio_for(js: Path) -> Path | None:
    # in-store CCTV clips are video: hand out only the sound, extracted once to a temp file then renamed
    audio = source_audio(js)
    if not audio or audio.suffix != ".mp4":
        return audio
    m4a = js.with_suffix(".m4a")
    with _extract:
        if not m4a.exists():
            tmp = m4a.with_name(f"{js.stem}.{os.getpid()}.partial.m4a")
            try:
                cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-vn", "-c:a", "copy", str(tmp)]
                subprocess.run(cmd, check=True)
                os.replace(tmp, m4a)
            finally:
                tmp.unlink(missing_ok=True)
    return m4a


def recording(cid: str) -> Path | None:
    c = _find(cid, rows=[])
    return audio_for(c.js) if c else None
