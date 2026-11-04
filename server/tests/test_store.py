import sqlite3

from review_app.store import db, sync_db


def test_sync_db_idempotent(galaxy: dict) -> None:
    assert sync_db() == 3 and sync_db() == 3
    with db() as c:
        assert c.execute("SELECT count(*) FROM conversations").fetchone()[0] == 3
        assert c.execute("SELECT count(*) FROM results WHERE system='gemma'").fetchone()[0] == 2
        assert c.execute("SELECT call_at, kind FROM conversations WHERE id=?", (galaxy["a"],)).fetchone() == (
            "2026-11-02T10:15:00+05:30",
            "call",
        )


def test_reviews_gain_source_column(settings) -> None:
    old = sqlite3.connect(settings.db)
    old.execute(
        "CREATE TABLE reviews (conv TEXT, system TEXT, user_id INTEGER, user_name TEXT, verdict TEXT, "
        "note TEXT, ts TEXT, PRIMARY KEY (conv, system, user_id))"
    )
    old.execute("INSERT INTO reviews VALUES ('c','pipeline',1,'Asha','ok','','t')")
    old.commit()
    old.close()
    for _ in range(2):
        with db() as c:
            assert c.execute("SELECT source FROM reviews").fetchall() == [(None,)]
