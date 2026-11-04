import json
import re

from .config import get_settings
from .roles import roles
from .telegram import call, keep_pinned, launch_url

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


def _button(url: str) -> dict:
    return {"inline_keyboard": [[{"text": "📝 Open review", "url": url}]]}


def pin_launcher() -> None:
    # one launcher message kept at the top of the group; later runs only refresh its button to the current tunnel
    st = get_settings()
    page = f"{st.origin}/audio-review-miniapp/?api={tunnel_sub()}"
    call("setChatMenuButton", menu_button={"type": "web_app", "text": "📝 Review", "web_app": {"url": page}})
    print(f"menu button -> {page}", flush=True)
    keep_pinned(st.chat, "review_pin.json", LAUNCHER_TEXT, _button(launch_url(tunnel_sub())), "HTML")


def pin_cost_launcher() -> None:
    cost_chat = get_settings().cost_chat
    if cost_chat:
        markup = _button(launch_url(tunnel_sub(), cost=True))
        keep_pinned(cost_chat, "review_pin_cost.json", COST_LAUNCHER_TEXT, markup, "HTML")


def card_text() -> str:
    # Telegram renders a t.me/<bot>/<app> link as a "Bot Application" card with an OPEN APP button
    return f"📝 Open the review app\n{launch_url(tunnel_sub())}"


def ensure_card() -> None:
    # direct-link card, pinned; its link is re-edited when the tunnel host changes
    keep_pinned(get_settings().chat, "review_card.json", card_text())


def ensure_owner() -> None:
    # the review group's creator owns the Team page; set once
    if roles().get("owner"):
        return
    st = get_settings()
    admins = call("getChatAdministrators", chat_id=st.chat)
    creator = next(a["user"] for a in admins if a["status"] == "creator")
    st.roles_file.write_text(json.dumps({"owner": creator["id"], "tech": []}))
    print(f"owner set: {creator.get('first_name', '')}", flush=True)
