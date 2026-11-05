import json
import socket

import pytest
from conftest import FakeTelegram

from review_app import devices
from review_app.config import Settings
from review_app.devices import DEVICES, check_devices, reachable, span, step

T0 = 1_800_000_000.0


def run(minutes: list, up: bool = False, **kw) -> None:
    for m in minutes:
        check_devices(now=T0 + m * 60, probe=lambda addr: up, **kw)


def texts(tg: FakeTelegram) -> list:
    return [p["text"] for m, p in tg.calls if m == "sendMessage"]


def test_span() -> None:
    assert [span(m) for m in (0, 5, 47, 60, 90, 125)] == ["0 min", "5 min", "47 min", "1 h", "1 h 30 min", "2 h 5 min"]


def test_step_schedule() -> None:
    s, ev, _ = step({}, False, T0)
    assert s == {"since": T0, "alerts": 0} and ev is None
    assert step(s, False, T0 + 9 * 60)[1] is None
    s, ev, mins = step(s, False, T0 + 10 * 60)
    assert ev == "down" and mins == 10 and s["alerts"] == 1
    s, ev, mins = step(s, False, T0 + 70 * 60)  # missed ticks: one alert for the latest step, not two
    assert ev == "down" and mins == 60 and s["alerts"] == 3
    assert step({}, True, T0) == ({}, None, 0)  # never alerted: no back-online note


def test_phone_alerts_at_10_30_60_90_then_quiet(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", INSTORE="false")
    run(range(0, 121))
    sent = texts(tg)
    posts = [p for m, p in tg.calls if m == "sendMessage"]
    assert len(sent) == 4 and all(p["chat_id"] == "-1" and p["parse_mode"] == "HTML" for p in posts)
    assert [s.split("offline (")[1].split(")")[0] for s in sent] == ["10 min", "30 min", "1 h", "1 h 30 min"]
    assert sent[0].startswith("📵 <b>Galaxy store phone is offline (10 min)</b>\n\n@Nikhil_mirajkar @Royjpr please")
    assert "3. Open Termux, type sshd and press Enter." in sent[0] and sent[0].endswith("Reply here when done.")
    assert sent[3].endswith("Last reminder. We will post here when it is back.")
    run([125], up=True)
    back = "✅ Galaxy store phone is back online (was down 2 h 5 min)."
    assert texts(tg)[-1] == back
    assert json.loads((settings.home / "devices_state.json").read_text()) == {"phone": {}}


def test_short_blip_and_restart_keep_quiet(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", INSTORE="false")
    run([0, 9])
    run([9.5], up=True)
    assert texts(tg) == []
    run([10, 19])  # down again from minute 10; state is on disk, so a restart picks up where it was
    assert texts(tg) == []
    run([20])
    assert "offline (10 min)" in texts(tg)[0]


def test_switched_off_types_are_not_checked(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", INSTORE="false", CALLS="false")
    seen = []
    check_devices(now=T0, probe=seen.append)
    assert seen == [] and texts(tg) == []
    set_env(INSTORE="true")
    run([0, 10])
    msg = texts(tg)[0]
    head, ask = msg.split("\n\n")
    assert head == "<b>Galaxy in-store Jetson is offline (10 min)</b>"
    assert ask == "@Nikhil_mirajkar @Royjpr please help bring it back online."
    assert [d.key for d in DEVICES] == ["phone", "jetson"]


def test_reachable() -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port = srv.getsockname()[1]
    assert reachable(f"127.0.0.1:{port}")
    srv.close()
    assert not reachable(f"127.0.0.1:{port}", timeout=1) and not reachable("bad")


def test_alerts_go_to_alert_chat_when_set(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", ALERT_CHAT="-4650652548", INSTORE="false")
    run([0, 10])
    assert [p["chat_id"] for m, p in tg.calls] == ["-4650652548"]


def msg(mid: int, text: str, user: str | None, uid: int, reply_to: int, at: float, **f) -> dict:
    m = {"message_id": mid, "chat": {"id": -1}, "date": int(T0 + at * 60), "text": text}
    m["from"] = {"id": uid, "first_name": "Ann", **({"username": user} if user else {}), **f}
    m["reply_to_message"] = {"message_id": reply_to}
    return {"update_id": mid, "message": m}


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> list:
    asked: list = []

    def fake(prompt: str) -> str:
        asked.append(prompt.split('replied:\n\n"')[1].split('"\n')[0])
        if "boom" in prompt:
            raise OSError("model down")
        return "yes" if any(w in prompt for w in ('"Done"', '"ho gaya"')) else "no"

    monkeypatch.setattr(devices, "ask_llm", fake)
    return asked


def test_done_reply_then_back_online_thanks_latest(settings: Settings, set_env, tg: FakeTelegram, llm: list) -> None:
    set_env(TG_CHAT="-1", INSTORE="false")
    run([0, 10])  # alert 101
    tg.results["getUpdates"] = [
        msg(1, "Done", "Royjpr", 8, 101, at=11),
        msg(2, "ok checking", "Nikhil_mirajkar", 7, 101, at=11),
        msg(3, "done", "some_bot", 9, 101, at=11, is_bot=True),
        msg(4, "Thanks", "haripratap", 11, 999, at=11),
        msg(5, "ho gaya", None, 12, 101, at=11),
    ]
    run([11, 11.5])
    assert llm == ["Done", "ok checking", "ho gaya"]  # each reply asked once, bots and other threads skipped
    run([12], up=True)
    assert texts(tg)[-1] == (
        '✅ Thanks, <a href="tg://user?id=12">Ann</a>. '
        "The Galaxy store phone is back online now (was down 12 min). Appreciate your support."
    )


def test_still_offline_5_min_after_done_and_reminder_paused(settings: Settings, set_env, tg, llm: list) -> None:
    set_env(TG_CHAT="-1", INSTORE="false")
    run([0, 10])  # alert 101
    tg.results["getUpdates"] = [msg(1, "Done", "Nikhil_mirajkar", 7, 101, at=22)]
    run(range(22, 27))
    assert len(texts(tg)) == 1  # under 5 min since the Done
    run([27])
    p = [p for m, p in tg.calls if m == "sendMessage"][-1]
    assert p["text"] == (
        "@Nikhil_mirajkar the Galaxy store phone is still offline. Please check the steps again and reply Done when "
        "finished."
    )
    assert p["reply_parameters"]["message_id"] == 1
    run(range(28, 61))
    sent = texts(tg)
    assert len(sent) == 3 and "offline (1 h)" in sent[2]  # 30 min reminder skipped; no second still-offline
    s = json.loads((settings.home / "devices_state.json").read_text())["phone"]
    assert s["msgs"] == [101, 103] and s["nudged"] == 1


def test_model_down_sends_plain_lines(settings: Settings, set_env, tg: FakeTelegram, llm: list) -> None:
    set_env(TG_CHAT="-1", INSTORE="false")
    run([0, 10])
    tg.results["getUpdates"] = [msg(1, "boom", "Nikhil_mirajkar", 7, 101, at=11)]
    run(range(11, 20))
    run([20], up=True)
    assert texts(tg)[-1] == "✅ Galaxy store phone is back online (was down 20 min)."
