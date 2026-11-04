import html
import json
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass

from .config import get_settings
from .telegram import call

ALERT_AT = (5, 30, 60, 90)  # minutes offline when an alert goes out; quiet after the last until back online
PHONE_STEPS = (
    "1. Keep the phone on, charging and connected to the internet.\n"
    "2. Open Tailscale and check it says Connected.\n"
    "3. Open Termux, type sshd and press Enter.\n"
    "4. Open Termux:Boot once."
)
LAST = "Last reminder. We will post here when it is back."


@dataclass(frozen=True)
class Device:
    key: str
    kind: str  # checked only while this type (CALLS / INSTORE) is on
    addr: str  # Settings field holding host:port
    down: str  # header; {d} = time offline
    ask: str  # {tag} = who is tagged
    up: str
    steps: str = ""
    reply: str = ""


DEVICES = (
    Device(
        "phone",
        "call",
        "phone_addr",
        "📵 <b>Galaxy store phone is offline ({d})</b>",
        "{tag} please ask the store staff to:",
        "✅ Galaxy store phone is back online (was down {d}).",
        PHONE_STEPS,
        "Reply here when done.",
    ),
    Device(
        "jetson",
        "in-store",
        "jetson_addr",
        "<b>Galaxy in-store Jetson is offline ({d})</b>",
        "{tag} please help bring it back online.",
        "✅ Galaxy in-store Jetson is back online (was down {d}).",
    ),
)


def reachable(addr: str, timeout: float = 5) -> bool:
    host, _, port = addr.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def span(mins: float) -> str:
    h, m = divmod(int(mins), 60)
    return " ".join(p for p in (f"{h} h" if h else "", f"{m} min" if m or not h else "") if p)


def step(prev: dict, up: bool, now: float) -> tuple[dict, str | None, float]:
    # returns (new state, "down"/"last"/"up"/None, minutes offline)
    if up:
        mins = (now - prev["since"]) / 60 if prev.get("since") else 0
        return {}, ("up" if prev.get("alerts") else None), mins
    since, sent = prev.get("since", now), prev.get("alerts", 0)
    mins = (now - since) / 60
    due = sum(mins >= a for a in ALERT_AT)
    if due > sent:
        return {"since": since, "alerts": due}, ("last" if due == len(ALERT_AT) else "down"), ALERT_AT[due - 1]
    return {"since": since, "alerts": sent}, None, mins


def message(d: Device, event: str, mins: float, tag: str) -> str:
    if event == "up":
        return d.up.format(d=span(mins))
    ask = d.ask.format(tag=html.escape(tag))
    body = f"{ask}\n{d.steps}" if d.steps else ask
    end = LAST if event == "last" else d.reply
    return "\n\n".join(p for p in (d.down.format(d=span(mins)), body, end) if p)


def check_devices(now: float | None = None, probe: Callable[[str], bool] = reachable) -> None:
    st = get_settings()
    state_f = st.home / "devices_state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {}
    now = time.time() if now is None else now
    for d in DEVICES:
        if not st.kind_on(d.kind):
            state.pop(d.key, None)
            continue
        state[d.key], event, mins = step(state.get(d.key, {}), probe(getattr(st, d.addr)), now)
        chat = st.alert_chat or st.chat
        if event and chat:
            call("sendMessage", chat_id=chat, text=message(d, event, mins, st.alert_tag), parse_mode="HTML")
            print(f"device {d.key} {event} ({span(mins)})", flush=True)
    state_f.write_text(json.dumps(state))
