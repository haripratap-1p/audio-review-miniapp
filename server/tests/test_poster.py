from pathlib import Path

from review_app.config import Settings
from review_app.poster import call_date, call_time, card, form, review_button


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


def test_form() -> None:
    assert form("text", "<b>Transcript</b>") == ["--form-string", "text=<b>Transcript</b>"]
    assert form("audio", Path("/a/b.m4a")) == ["-F", "audio=@/a/b.m4a"]


def test_call_time() -> None:
    assert call_time("20261102_154507") > call_time("919620356029_20261028-104047")


def test_review_button(settings: Settings) -> None:
    assert review_button("Galaxy/x") == {}
    settings.tunnel_log.write_text("https://abc-def.trycloudflare.com\n")
    assert "startapp=abc-def__" in review_button("Galaxy/x")["reply_markup"]
