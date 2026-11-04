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
    "1️⃣ Check the phone is switched on, plugged into the charger, and connected to Wi-Fi or mobile data.\n"
    "2️⃣ Open the <b>Tailscale</b> app. It should say <b>Connected</b>. If it does not, tap the switch to connect.\n"
    "3️⃣ Open the <b>Termux</b> app (black screen). Type <b>sshd</b> and press <b>Enter</b>. "
    "Nothing appears on screen; that is normal.\n"
    "4️⃣ Open the <b>Termux:Boot</b> app once. It opens and closes by itself; that is normal."
)
LAST = "This is the last reminder; we will post here when it is back online."


@dataclass(frozen=True)
class Device:
    key: str
    kind: str  # checked only while this type (CALLS / INSTORE) is on
    addr: str  # Settings field holding host:port
    down: str  # first line; {d} = time offline, {tag} = who is tagged
    up: str
    steps: str = ""
    reply: str = ""


DEVICES = (
    Device(
        "phone",
        "call",
        "phone_addr",
        "📵 Galaxy store phone is offline — call recordings are not reaching us (down {d}). "
        "{tag} please coordinate with the store staff:",
        "✅ Galaxy store phone is back online — call recordings are reaching us again (was down {d}).",
        PHONE_STEPS,
        "Please reply here when done. We will confirm here once the phone is back online.",
    ),
    Device(
        "jetson",
        "in-store",
        "jetson_addr",
        "Galaxy in-store Jetson is offline — in-store conversations are not reaching us (down {d}). "
        "{tag} please coordinate to bring it back online.",
        "✅ Galaxy in-store Jetson is back online — in-store conversations are reaching us again (was down {d}).",
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
    text = d.down.format(d=span(mins), tag=html.escape(tag))
    if d.steps:
        text += "\n" + d.steps
    end = LAST if event == "last" else d.reply
    return text + ("\n\n" + end if end else "")


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
        if event and st.chat:
            call("sendMessage", chat_id=st.chat, text=message(d, event, mins, st.alert_tag), parse_mode="HTML")
            print(f"device {d.key} {event} ({span(mins)})", flush=True)
    state_f.write_text(json.dumps(state))
