import json
import sqlite3
from datetime import datetime

from .config import IST, PIPELINE_MODEL, SYSTEMS, get_settings
from .results import collect, load

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
"""


def db() -> sqlite3.Connection:
    c = sqlite3.connect(get_settings().db, timeout=10)
    c.executescript(SCHEMA)
    return c


def all_rows() -> list:
    with db() as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM reviews")]


def sync_db() -> int:
    # temporary: mirror the result files into SQLite (files stay the source of truth for now)
    now = datetime.now(IST).isoformat(timespec="seconds")
    items = collect([])
    with db() as c:
        for i in items:
            js, s = i["_js"], i["sort"]
            audio = next(js.parent.joinpath("audio").glob(js.stem + ".*"), None)
            c.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "duration=excluded.duration, audio_path=excluded.audio_path",
                (
                    i["id"],
                    i["key"],
                    i["store"],
                    (load(js) or {}).get("adminId", ""),
                    i["kind"],
                    i["who"],
                    f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}+05:30",
                    i["duration"],
                    str(audio or ""),
                    now,
                ),
            )
            for system in SYSTEMS:
                r = i[system]
                if r:
                    c.execute(
                        "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            i["id"],
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
    return len(items)
