import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from review_app import http, judge, telegram, viewer
from review_app.config import Settings, get_settings
from review_app.conversations import conv_id
from review_app.http import Handler
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
    "GEMINI_API_KEYS",
    "JUDGE_MODEL",
    "JUDGE_DAILY_CAP",
    "JUDGE_PRICE_IN",
    "JUDGE_PRICE_OUT",
    "CALLS",
    "INSTORE",
    "PHONE_ADDR",
    "JETSON_ADDR",
    "ALERT_TAG",
    "ALERT_CHAT",
    "LLM_URL",
    "LLM_MODEL",
    "UPLOADER_BEAT",
)
TOKEN = "123:abc"


class FakeTelegram:
    def __init__(self) -> None:
        self.calls: list = []  # (method, params)
        self.fail: dict = {}  # method -> error description raised once
        self.next_id = 100
        self.results: dict = {"getUpdates": []}  # method -> reply

    def call(self, method: str, **params: object) -> object:
        self.calls.append((method, params))
        if method in self.fail:
            raise telegram.TelegramError(f"{method}: {self.fail.pop(method)}")
        if method.startswith("send"):
            self.next_id += 1
            return {"message_id": self.next_id}
        return self.results.get(method, True)

    def methods(self) -> list:
        return [m for m, _ in self.calls]


class FakeGemini:
    def __init__(self) -> None:
        self.calls: list = []  # (model, key, body)
        self.replies: list = []  # (status, json) used in order; then every line "same"

    def post(self, model: str, key: str, body: dict) -> tuple[int, dict]:
        self.calls.append((model, key, body))
        if self.replies:
            return self.replies.pop(0)
        n = body["contents"][0]["parts"][0]["text"].split("SYSTEM LINES:\n")[1].count("\n") + 1
        return 200, reply([{"line": i, "meaning": "same"} for i in range(1, n + 1)])


def reply(lines: object, tokens: tuple = (1000, 100, 50)) -> dict:
    text = json.dumps({"lines": lines}) if not isinstance(lines, str) else lines
    p, c, t = tokens
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": p, "candidatesTokenCount": c, "thoughtsTokenCount": t},
    }


class FakeMembership:
    def __init__(self) -> None:
        self.chats: dict = {}  # chat -> set of user ids

    def is_member(self, uid: int, chat: str) -> bool:
        return uid in self.chats.get(chat, set())


@pytest.fixture(autouse=True)
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    for k in ENV_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REVIEW_HOME", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(viewer, "membership", FakeMembership())
    monkeypatch.setattr(telegram, "client", FakeTelegram())
    monkeypatch.setattr(judge, "client", FakeGemini())
    http._writes.clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def tg() -> FakeTelegram:
    return telegram.client


@pytest.fixture
def gemini() -> FakeGemini:
    return judge.client


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
            c.execute(
                "INSERT INTO reviews (conv, system, user_id, user_name, verdict, note, ts) VALUES (?,?,?,?,?,?,?)", row
            )
    return {"a": a, "b": b, "results": settings.results}


CHAT, COST_CHAT = "-1", "-100"


@pytest.fixture
def api(set_env: Callable, fields: dict) -> Iterator[Callable[..., tuple]]:
    # the real Handler on an ephemeral port; members: client group 1-9, cost group 20-29
    set_env(TG_TOKEN=TOKEN, TG_CHAT=CHAT, TG_COST_CHAT=COST_CHAT)
    viewer.membership.chats = {CHAT: set(range(1, 10)), COST_CHAT: set(range(20, 30))}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, args=(0.05,), daemon=True).start()

    def call(path: str, uid: int, launch: str = "sub", body: dict | None = None, tamper: bool = False) -> tuple:
        user = json.dumps({"id": uid, "first_name": f"U{uid}"})
        init = sign({**fields, "user": user, "start_param": launch})
        init = init.replace("U", "X") if tamper else init
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}{path}", data, {"X-Init-Data": init})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    call.port = srv.server_port  # type: ignore[attr-defined]
    yield call
    srv.shutdown()
    srv.server_close()
