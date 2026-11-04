import json
from collections.abc import Callable

from conftest import FakeTelegram

from review_app.config import Settings
from review_app.launcher import ensure_card, pin_cost_launcher, pin_launcher


def url_of(params: dict) -> str:
    return params["reply_markup"]["inline_keyboard"][0][0]["url"]


def test_launcher_pinned_message_flow(settings: Settings, set_env: Callable, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", TG_COST_CHAT="-100")
    settings.tunnel_log.write_text("https://aaa.trycloudflare.com\n")
    pin_launcher()  # first run: post and pin
    assert tg.methods() == ["setChatMenuButton", "sendMessage", "pinChatMessage"]
    assert url_of(tg.calls[1][1]).endswith("?startapp=aaa") and tg.calls[1][1]["parse_mode"] == "HTML"
    assert json.loads((settings.home / "review_pin.json").read_text()) == {"message_id": 101}
    tg.calls.clear()
    settings.tunnel_log.write_text("https://bbb.trycloudflare.com\n")
    pin_launcher()  # edit ok: same message, new button
    assert tg.methods() == ["setChatMenuButton", "editMessageReplyMarkup", "pinChatMessage"]
    assert tg.calls[1][1]["message_id"] == 101 and url_of(tg.calls[1][1]).endswith("?startapp=bbb")
    tg.calls.clear()
    tg.fail["editMessageReplyMarkup"] = "Bad Request: message is not modified"
    pin_launcher()  # not modified: keep it
    assert tg.methods() == ["setChatMenuButton", "editMessageReplyMarkup", "pinChatMessage"]
    tg.calls.clear()
    tg.fail["editMessageReplyMarkup"] = "Bad Request: message to edit not found"
    pin_launcher()  # message gone: post a new one
    assert tg.methods() == ["setChatMenuButton", "editMessageReplyMarkup", "sendMessage", "pinChatMessage"]
    assert json.loads((settings.home / "review_pin.json").read_text()) == {"message_id": 102}


def test_cost_launcher_and_card(settings: Settings, set_env: Callable, tg: FakeTelegram) -> None:
    set_env(TG_CHAT="-1", TG_COST_CHAT="-100")
    settings.tunnel_log.write_text("https://aaa.trycloudflare.com\n")
    pin_cost_launcher()
    assert tg.calls[0][1]["chat_id"] == "-100" and url_of(tg.calls[0][1]).endswith("?startapp=aaa____cost")
    assert (settings.home / "review_pin_cost.json").exists()
    tg.calls.clear()
    ensure_card()
    ensure_card()  # second run edits the card's text
    assert tg.methods() == ["sendMessage", "pinChatMessage", "editMessageText", "pinChatMessage"]
    assert tg.calls[2][1]["text"].endswith("?startapp=aaa") and "reply_markup" not in tg.calls[0][1]
