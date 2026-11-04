import json
import socket

from conftest import FakeTelegram

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
    assert step(s, False, T0 + 4 * 60)[1] is None
    s, ev, mins = step(s, False, T0 + 5 * 60)
    assert ev == "down" and mins == 5 and s["alerts"] == 1
    s, ev, mins = step(s, False, T0 + 70 * 60)  # missed ticks: one alert for the latest step, not two
    assert ev == "down" and mins == 60 and s["alerts"] == 3
    assert step({}, True, T0) == ({}, None, 0)  # never alerted: no back-online note


def test_phone_alerts_at_5_30_60_90_then_quiet(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", INSTORE="false")
    run(range(0, 121))
    sent = texts(tg)
    assert len(sent) == 4 and all(p["chat_id"] == "-1" and p["parse_mode"] == "HTML" for m, p in tg.calls)
    assert [s.split("offline (")[1].split(")")[0] for s in sent] == ["5 min", "30 min", "1 h", "1 h 30 min"]
    assert sent[0].startswith("📵 <b>Galaxy store phone is offline (5 min)</b>\n\n@Nikhil_mirajkar @Royjpr please")
    assert "3. Open Termux, type sshd and press Enter." in sent[0] and sent[0].endswith("Reply here when done.")
    assert sent[3].endswith("Last reminder. We will post here when it is back.")
    run([125], up=True)
    back = "✅ Galaxy store phone is back online (was down 2 h 5 min)."
    assert texts(tg)[-1] == back
    assert json.loads((settings.home / "devices_state.json").read_text()) == {"phone": {}}


def test_short_blip_and_restart_keep_quiet(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", INSTORE="false")
    run([0, 3])
    run([4], up=True)
    assert texts(tg) == []
    run([10, 14])  # down again from minute 10; state is on disk, so a restart picks up where it was
    assert texts(tg) == []
    run([15])
    assert "offline (5 min)" in texts(tg)[0]


def test_switched_off_types_are_not_checked(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", INSTORE="false", CALLS="false")
    seen = []
    check_devices(now=T0, probe=seen.append)
    assert seen == [] and texts(tg) == []
    set_env(INSTORE="true")
    run([0, 5])
    msg = texts(tg)[0]
    head, ask = msg.split("\n\n")
    assert head == "<b>Galaxy in-store Jetson is offline (5 min)</b>"
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
    run([0, 5])
    assert [p["chat_id"] for m, p in tg.calls] == ["-4650652548"]
