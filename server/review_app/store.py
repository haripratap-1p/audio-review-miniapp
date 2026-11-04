import json
import sqlite3
from datetime import datetime

from .config import IST, PIPELINE_MODEL, SYSTEMS, get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY, key TEXT UNIQUE, store TEXT, admin_id TEXT, kind TEXT, who TEXT,
    call_at TEXT, duration TEXT, audio_path TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS results (
    conv TEXT REFERENCES conversations(id), system TEXT, sentiment TEXT, summary TEXT, turns_json TEXT,
    secs REAL, model TEXT, error TEXT, updated_at TEXT, PRIMARY KEY (conv, system));
CREATE TABLE IF NOT EXISTS reviews (
    conv TEXT, system TEXT, user_id INTEGER, user_name TEXT, verdict TEXT, note TEXT, ts TEXT,
    PRIMARY KEY (conv, system, user_id));
CREATE TABLE IF NOT EXISTS visitors (user_id INTEGER PRIMARY KEY, name TEXT, username TEXT, last_seen TEXT);
CREATE TABLE IF NOT EXISTS line_reviews (
    conv TEXT, system TEXT, line INTEGER, user_id INTEGER, user_name TEXT, verdict TEXT, note TEXT, ts TEXT,
    PRIMARY KEY (conv, system, line, user_id));
CREATE TABLE IF NOT EXISTS judge_lines (
    conv TEXT, system TEXT, line INTEGER, meaning TEXT, PRIMARY KEY (conv, system, line));
CREATE TABLE IF NOT EXISTS judge_runs (
    conv TEXT, system TEXT, score REAL, ref_model TEXT, model TEXT, tokens_in INTEGER, tokens_out INTEGER,
    cost_usd REAL, ts TEXT, PRIMARY KEY (conv, system));
"""


def db() -> sqlite3.Connection:
    c = sqlite3.connect(get_settings().db, timeout=10)
    c.executescript(SCHEMA)
    if "source" not in {r[1] for r in c.execute("PRAGMA table_info(reviews)")}:
        try:
            c.execute("ALTER TABLE reviews ADD COLUMN source TEXT")  # "team" | "analysis"; NULL = before sources
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e):  # another process added it first
                raise
    return c


def all_rows() -> list:
    with db() as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM reviews")]


def sync_db() -> int:
    # temporary: mirror the result files into SQLite (files stay the source of truth for now)
    from .conversations import scan  # conversations imports store

    now = datetime.now(IST).isoformat(timespec="seconds")
    convs = scan(rows=[])
    with db() as c:
        for i in convs:
            s = i.sort
            c.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "duration=excluded.duration, audio_path=excluded.audio_path",
                (
                    i.id,
                    i.key,
                    i.store,
                    i.admin_id,
                    i.kind,
                    i.who,
                    f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}+05:30",
                    i.duration,
                    str(i.audio or ""),
                    now,
                ),
            )
            for system in SYSTEMS:
                r = i.results[system]
                if r:
                    c.execute(
                        "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            i.id,
                            system,
                            r.get("sentiment", ""),
                            r.get("summary", ""),
                            json.dumps(r.get("turns", []), ensure_ascii=False),
                            r.get("secs"),
                            r.get("model") or PIPELINE_MODEL,
                            r.get("error", ""),
                            now,
                        ),
                    )
    return len(convs)


def judged(conv: str | None = None) -> dict:
    # (conv, system) -> {"score", "ref_model", "lines": {"<idx>": meaning}}; lines only for one conv
    with db() as c:
        q = "SELECT conv, system, score, ref_model FROM judge_runs" + (" WHERE conv=?" if conv else "")
        out = {
            (cv, s): {"score": sc, "ref_model": rm, "lines": {}}
            for cv, s, sc, rm in c.execute(q, (conv,) if conv else ())
        }
        if conv:
            for s, ln, m in c.execute("SELECT system, line, meaning FROM judge_lines WHERE conv=?", (conv,)):
                if (conv, s) in out:
                    out[(conv, s)]["lines"][str(ln)] = m
    return out
