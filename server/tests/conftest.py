import hashlib
import hmac
import json
import time
import urllib.parse
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from review_app import results, telegram, views
from review_app.config import Settings, get_settings
from review_app.results import conv_id
from review_app.store import db

ENV_VARS = (
    "TG_TOKEN",
    "TG_CHAT",
    "TG_COST_CHAT",
    "POST_FROM",
    "REVIEW_ORIGIN",
    "REVIEW_APP_LINK",
    "REVIEW_PORT",
    "RESULTS_BASE",
    "REVIEW_DB",
    "REVIEW_HOME",
)
TOKEN = "123:abc"


@pytest.fixture(autouse=True)
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    for k in ENV_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REVIEW_HOME", str(tmp_path))
    get_settings.cache_clear()
    results._cache.clear()
    telegram._members.clear()
    views._writes.clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def set_env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Settings]:
    def apply(**env: str) -> Settings:
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return get_settings()

    return apply


def sign(fields: dict, token: str = TOKEN) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urllib.parse.urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})


@pytest.fixture
def fields() -> dict:
    return {"auth_date": str(int(time.time())), "query_id": "q", "user": json.dumps({"id": 7, "first_name": "Asha"})}


@pytest.fixture
def galaxy(settings: Settings) -> dict:
    day = settings.results / "Galaxy" / "2026-11-02"
    day.mkdir(parents=True)
    for stem, gem in (
        ("919800000001_20261102-101500", True),
        ("919800000002_20261102-111500", True),
        ("20261102_154507", False),
    ):
        (day / f"{stem}.json").write_text(json.dumps({"conversation": "[Speaker_01]: hi", "sentiment": "NEUTRAL"}))
        if gem:
            gemma = {"turns": [{"speaker": "Speaker 1", "text": "hi"}], "sentiment": "NEUTRAL", "secs": 40}
            (day / f"{stem}.gemma.json").write_text(json.dumps(gemma))
    lfm = {"turns": [{"speaker": "Speaker", "text": "hi"}]}
    (day / "919800000001_20261102-101500.lfm.json").write_text(json.dumps(lfm))
    (day / "20261102_154507.lfm.json").write_text(json.dumps({"skipped": "language not supported", "turns": []}))
    a, b = conv_id("Galaxy/919800000001_20261102-101500"), conv_id("Galaxy/919800000002_20261102-111500")
    with db() as c:
        for row in (
            (a, "pipeline", 1, "Asha", "ok", "", "2026-11-02T18:00"),
            (a, "gemma", 1, "Asha", "ok", "clear speech", "2026-11-02T18:01"),
            (b, "pipeline", 1, "Asha", "bad", "", "2026-11-02T18:02"),
        ):
            c.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?)", row)
    return {"a": a, "b": b, "results": settings.results}
