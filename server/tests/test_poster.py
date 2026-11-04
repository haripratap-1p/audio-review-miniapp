import json
from pathlib import Path

import pytest
from conftest import FakeTelegram

from review_app.config import Settings
from review_app.conversations import conv_id
from review_app.poster import call_date, call_time, card, post, review_button, skip


def test_call_date() -> None:
    assert call_date("919620356029_20261028-104047") == "2026-10-28"
    assert call_date("Pooja_Patil_Agency_20260622-133803") == "2026-06-22"
    assert call_date("junk") == "" < "2026-10-28"
    assert call_date("20261102_154507") == "2026-11-02"


def test_card() -> None:
    assert "· Piyush Kumar\n🕒 22-06-2026 09:55" in card("Galaxy", "Piyush_Kumar__20260622-095559", {})
    assert "· 919620356029\n🕒 28-10-2026 10:40" in card("Galaxy", "919620356029_20261028-104047", {})
    assert card("Galaxy-instore", "20261102_154507", {}).startswith(
        "🏪 <b>Galaxy-instore</b> · In-store\n🕒 02-11-2026 15:45"
    )
    assert card("Galaxy", "Piyush_Kumar__20260622-095559", {}).startswith("📞")


def test_call_time() -> None:
    assert call_time("20261102_154507") > call_time("919620356029_20261028-104047")
    assert call_time("20261102_154507") == "202611021545"  # to the minute: post order unchanged


def test_review_button(settings: Settings) -> None:
    assert review_button("Galaxy/x") == {}
    settings.tunnel_log.write_text("https://abc-def.trycloudflare.com\n")
    url = review_button("Galaxy/x")["reply_markup"]["inline_keyboard"][0][0]["url"]
    assert url.endswith(f"?startapp=abc-def__{conv_id('Galaxy/x')}")


def test_post_end_to_end(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1")
    settings.tunnel_log.write_text("https://abc-def.trycloudflare.com\n")
    day = settings.results / "Galaxy" / "2026-11-02"
    (day / "audio").mkdir(parents=True)
    js = day / "919800000001_20261102-101500.json"
    js.write_text(json.dumps({"conversation": "[Speaker_01]: hi <there>", "summary": "greeting"}))
    (day / "audio" / f"{js.stem}.mp3").write_bytes(b"mp3")
    key, posted = f"Galaxy/{js.stem}", set()
    post(key, js, posted)
    (m1, audio), (m2, msg) = tg.calls
    assert m1 == "sendAudio" and audio["audio"] == day / "audio" / f"{js.stem}.mp3" and audio["chat_id"] == "-1"
    assert "<b>Galaxy</b> · 919800000001" in audio["caption"] and "greeting" in audio["caption"]
    assert m2 == "sendMessage" and msg["text"] == "<b>Transcript</b>\n[Speaker_01]: hi &lt;there&gt;"
    assert msg["reply_markup"]["inline_keyboard"][0][0]["text"] == "📝 Review"
    assert json.loads((settings.results.parent / "telegram_msgids.json").read_text()) == {key: 101}
    assert key + "#card" in posted
    tg.fail["sendMessage"] = "Too Many Requests"
    tg.calls.clear()
    with pytest.raises(RuntimeError):
        post(key, js, posted)  # transcript failed: a retry never resends the audio
    post(key, js, posted)
    assert tg.methods() == ["sendMessage", "sendMessage"]


def test_post_long_transcript_as_document(settings: Settings, set_env, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1")
    day = settings.results / "Galaxy" / "2026-11-02"
    day.mkdir(parents=True)
    js = day / "20261102_154507.json"
    js.write_text(json.dumps({"conversation": "[Speaker_01]: " + "x" * 4000}))
    post("Galaxy/20261102_154507", js, set())
    assert tg.methods() == ["sendMessage", "sendDocument"]  # no audio: card as text
    assert tg.calls[1][1]["document"] == Path(js.with_suffix(".txt")) and "reply_markup" not in tg.calls[1][1]


def test_skip_switched_off_types(set_env) -> None:
    call, clip = "919620356029_20261028-104047", "20261102_154507"
    assert not skip(call) and not skip(clip)
    set_env(INSTORE="false")
    assert skip(clip) and not skip(call)
    set_env(INSTORE="true", CALLS="false")
    assert skip(call) and not skip(clip)
