import json
import re
import urllib.error

from .config import get_settings
from .roles import roles
from .telegram import tg_api

LAUNCHER_TEXT = (
    "📝 <b>Review the audio pipeline</b>\nTap the button, play each conversation and mark the transcript "
    "✅ Correct or ❌ Wrong (add a note when wrong). Daily summary here at 7 PM."
)

COST_LAUNCHER_TEXT = (
    "📝 <b>Review — all models</b>\nOpens every conversation with the audio pipeline and each model "
    "side by side, plus the Benchmark. Only members of this group can open it."
)


def tunnel_sub() -> str:
    # quick-tunnel host changes on every restart; read the latest one from its log
    log = get_settings().tunnel_log
    subs = re.findall(r"https://([a-z0-9-]+)\.trycloudflare\.com", log.read_text()) if log.exists() else []
    return subs[-1] if subs else ""


def pin_cost_launcher() -> None:
    cost_chat = get_settings().cost_chat
    if cost_chat:
        pin_launcher(cost_chat, "review_pin_cost.json", "____cost", COST_LAUNCHER_TEXT, menu=False)


def pin_launcher(
    chat: str = "", state_name: str = "review_pin.json", suffix: str = "", text: str = LAUNCHER_TEXT, menu: bool = True
) -> None:
    # one launcher message kept at the top of the group; later runs only refresh its button to the current tunnel
    st = get_settings()
    chat, state = chat or st.chat, st.home / state_name
    if menu:
        page = f"{st.origin}/audio-review-miniapp/?api={tunnel_sub()}"
        tg_api("setChatMenuButton", menu_button={"type": "web_app", "text": "📝 Review", "web_app": {"url": page}})
        print(f"menu button -> {page}", flush=True)
    markup = {
        "inline_keyboard": [[{"text": "📝 Open review", "url": f"{st.app_link}?startapp={tunnel_sub()}{suffix}"}]]
    }
    mid = json.loads(state.read_text())["message_id"] if state.exists() else None
    if mid:
        try:
            tg_api("editMessageReplyMarkup", chat_id=chat, message_id=mid, reply_markup=markup)
            print(f"updated launcher {mid}", flush=True)
        except urllib.error.HTTPError as e:
            if "not modified" not in e.read().decode():
                mid = None  # launcher gone, post a new one
            else:
                print(f"launcher {mid} already current", flush=True)
    if not mid:
        mid = tg_api("sendMessage", chat_id=chat, text=text, parse_mode="HTML", reply_markup=markup)["result"][
            "message_id"
        ]
        state.write_text(json.dumps({"message_id": mid}))
        print(f"posted launcher {mid} in {chat}", flush=True)
    try:
        tg_api("pinChatMessage", chat_id=chat, message_id=mid, disable_notification=True)
        print(f"pinned launcher {mid}", flush=True)
    except urllib.error.HTTPError:
        print(f"bot can't pin launcher {mid}: make it a group admin with 'Pin messages'", flush=True)


def card_text() -> str:
    # Telegram renders a t.me/<bot>/<app> link as a "Bot Application" card with an OPEN APP button
    return f"📝 Open the review app\n{get_settings().app_link}?startapp={tunnel_sub()}"


def ensure_card() -> None:
    # direct-link card, pinned; its link is re-edited when the tunnel host changes
    st = get_settings()
    state = st.home / "review_card.json"
    mid = json.loads(state.read_text())["message_id"] if state.exists() else None
    if mid:
        try:
            tg_api("editMessageText", chat_id=st.chat, message_id=mid, text=card_text())
            print(f"updated card {mid}", flush=True)
            return
        except urllib.error.HTTPError as e:
            if "not modified" in e.read().decode():
                return
    mid = tg_api("sendMessage", chat_id=st.chat, text=card_text())["result"]["message_id"]
    state.write_text(json.dumps({"message_id": mid}))
    try:
        tg_api("pinChatMessage", chat_id=st.chat, message_id=mid, disable_notification=True)
    except urllib.error.HTTPError:
        print(f"posted card {mid}; could not pin", flush=True)


def ensure_owner() -> None:
    # the review group's creator owns the Team page; set once
    if roles().get("owner"):
        return
    st = get_settings()
    admins = tg_api("getChatAdministrators", chat_id=st.chat)["result"]
    creator = next(a["user"] for a in admins if a["status"] == "creator")
    st.roles_file.write_text(json.dumps({"owner": creator["id"], "tech": []}))
    print(f"owner set: {creator.get('first_name', '')}", flush=True)
