import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import TOKEN, sign

from review_app import telegram
from review_app.telegram import build_link, check_init_data, mode, parse_link


def test_check_init_data(fields: dict) -> None:
    good = sign(fields)
    assert check_init_data(good, TOKEN)["id"] == 7
    assert check_init_data(good, "123:other") is None
    assert check_init_data(good.replace("Asha", "Mallory"), TOKEN) is None
    assert check_init_data(good, TOKEN, max_age=-1) is None


def test_mode_with_cost_group(fields: dict, set_env: Callable) -> None:
    set_env(TG_COST_CHAT="-100")
    assert [mode(s) for s in ("sub", "sub__abc", "sub____cost", "sub__abc__cost", "sub__abc__costly")] == [
        "client",
        "client",
        "cost",
        "cost",
        "client",
    ]
    signed = sign({**fields, "start_param": "sub____cost"})
    assert mode(check_init_data(signed, TOKEN)["_sp"]) == "cost"
    assert check_init_data(signed.replace("sub____cost", "sub____costx"), TOKEN) is None  # can't edit a signed link


def test_mode_without_cost_group() -> None:
    assert mode("sub____cost") == "client"  # no cost group configured: never the full view


def test_link_round_trip() -> None:
    assert build_link("sub") == "sub" and build_link("sub", cost=True) == "sub____cost"
    assert build_link("sub", "abc") == "sub__abc" and build_link("sub", "abc", cost=True) == "sub__abc__cost"
    for args in (("sub", "", False), ("sub", "abc", False), ("sub", "", True), ("sub", "abc", True)):
        assert parse_link(build_link(*args)) == args


def test_http_client_retries_and_uploads(tmp_path: Path, set_env: Callable, monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(TG_TOKEN=TOKEN)
    seen: list = []

    class Bot(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen.append((self.path, self.headers["Content-Type"], self.rfile.read(int(self.headers["Content-Length"]))))
            if len(seen) == 1:
                body, code = {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 2}}, 429
            elif len(seen) == 2:
                body, code = {"ok": True, "result": {"message_id": 5}}, 200
            else:
                body, code = {"ok": False, "description": "Bad Request: message is not modified"}, 400
            self.send_response(code)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a: object) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Bot)
    threading.Thread(target=srv.serve_forever, args=(0.05,), daemon=True).start()
    sleeps: list = []
    monkeypatch.setattr(telegram.time, "sleep", sleeps.append)
    c = telegram.HttpClient()
    c.base = f"http://127.0.0.1:{srv.server_port}"
    (tmp_path / "a.m4a").write_bytes(b"SOUND")
    assert c.call("sendAudio", chat_id="-1", audio=tmp_path / "a.m4a", caption="<b>x</b>") == {"message_id": 5}
    assert sleeps == [3] and seen[0][2] == seen[1][2] and seen[1][0] == f"/bot{TOKEN}/sendAudio"
    assert seen[1][1].startswith("multipart/form-data; boundary=")
    body = seen[1][2]
    assert b'name="audio"; filename="a.m4a"' in body and b"SOUND" in body and b"<b>x</b>" in body
    with pytest.raises(telegram.TelegramError, match="sendMessage: Bad Request: message is not modified") as e:
        c.call("sendMessage", chat_id="-1", text="hi", reply_markup={"a": 1})
    assert TOKEN not in str(e.value) and json.loads(seen[2][2])["reply_markup"] == {"a": 1}
    srv.shutdown()
    srv.server_close()
