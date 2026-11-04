import html
import json
import socket
import time
import urllib.request
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
THANKS = "✅ Thanks, {who}. The Galaxy {name} is back online now (was down {d}). Appreciate your support."
STILL = "{who} the Galaxy {name} is still offline. Please {again} and reply Done when finished."
WAIT = 5 * 60  # seconds after a "Done" before saying it is still offline; reminders pause as long after that
ASK = (
    'Our bot posted an alert that the Galaxy {name} is offline and asked the staff to fix it and reply "Done" when '
    'finished. Someone replied:\n\n"{text}"\n\nIs this reply saying they finished the steps, fixed it, or that it is '
    'back online? A short "done", "ok done", "completed" or "ho gaya" counts as yes. Questions, "checking", '
    '"will do", "not working" are no. Answer with one word: yes or no.'
)


@dataclass(frozen=True)
class Device:
    key: str
    kind: str  # checked only while this type (CALLS / INSTORE) is on
    addr: str  # Settings field holding host:port
    down: str  # header; {d} = time offline
    ask: str  # {tag} = who is tagged
    up: str
    name: str  # in the thanks / still-offline lines
    again: str  # what the still-offline line asks them to redo
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
        "store phone",
        "check the steps again",
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
        "in-store Jetson",
        "check it again",
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
        return {**prev, "since": since, "alerts": due}, ("last" if due == len(ALERT_AT) else "down"), ALERT_AT[due - 1]
    return {**prev, "since": since, "alerts": sent}, None, mins


def message(d: Device, event: str, mins: float, tag: str) -> str:
    if event == "up":
        return d.up.format(d=span(mins))
    ask = d.ask.format(tag=html.escape(tag))
    body = f"{ask}\n{d.steps}" if d.steps else ask
    end = LAST if event == "last" else d.reply
    return "\n\n".join(p for p in (d.down.format(d=span(mins)), body, end) if p)


def ask_llm(prompt: str) -> str:
    st = get_settings()
    body = {
        "model": st.llm_model,
        "max_tokens": 3,
        "temperature": 0,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    req = urllib.request.Request(
        f"{st.llm_url}/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:  # shares the model with the Gemma worker, so it can queue
        return json.load(r)["choices"][0]["message"]["content"]


def _who(f: dict) -> str:
    if f.get("username"):
        return "@" + html.escape(f["username"])
    return f'<a href="tg://user?id={int(f["id"])}">{html.escape(f.get("first_name") or "there")}</a>'


def read_replies(d: Device, s: dict, chat: str) -> None:
    # new human replies to this outage's alerts go into s["replies"] as id -> [who, sent at, said done]
    got = s.setdefault("replies", {})
    for u in call("getUpdates", offset=-100) or []:
        m = u.get("message") or {}
        f, text, mid = m.get("from") or {}, m.get("text") or m.get("caption") or "", str(m.get("message_id"))
        to_us = (m.get("reply_to_message") or {}).get("message_id") in s.get("msgs", [])
        if to_us and text and not f.get("is_bot") and mid not in got and str(m["chat"]["id"]) == str(chat):
            yes = ask_llm(ASK.format(name=d.name, text=text)).strip().lower().startswith("yes")
            got[mid] = [_who(f), m.get("date", 0), yes]


def latest_done(s: dict) -> tuple[int, list] | None:
    return max(((int(k), v) for k, v in s.get("replies", {}).items() if v[2]), default=None)


def check_devices(now: float | None = None, probe: Callable[[str], bool] = reachable) -> None:
    st = get_settings()
    state_f = st.home / "devices_state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {}
    now = time.time() if now is None else now
    chat = st.alert_chat or st.chat
    for d in DEVICES:
        if not st.kind_on(d.kind):
            state.pop(d.key, None)
            continue
        prev = state.get(d.key, {})
        if prev.get("msgs") and chat:
            try:
                read_replies(d, prev, chat)
            except Exception as e:  # model or Telegram down: plain alerts still go out, retried next minute
                print(f"device {d.key} replies not read: {type(e).__name__}", flush=True)
        s, event, mins = step(prev, probe(getattr(st, d.addr)), now)
        state[d.key] = s
        if not chat:
            continue
        done = latest_done(prev)
        if event == "up":
            who = done[1][0] if done else ""
            text = THANKS.format(who=who, name=d.name, d=span(mins)) if who else d.up.format(d=span(mins))
            call("sendMessage", chat_id=chat, text=text, parse_mode="HTML")
        elif s.get("since") and done and done[0] != s.get("nudged") and now - done[1][1] >= WAIT:
            text = STILL.format(who=done[1][0], name=d.name, again=d.again)
            reply = {"message_id": done[0], "allow_sending_without_reply": True}
            call("sendMessage", chat_id=chat, text=text, parse_mode="HTML", reply_parameters=reply)
            s["nudged"], s["nudged_at"] = done[0], now
            print(f"device {d.key} still offline after a Done", flush=True)
        if event in ("down", "last"):
            if now - s.get("nudged_at", 0) < WAIT:
                print(f"device {d.key} {event} skipped: still-offline reply just sent", flush=True)
                continue
            sent = call("sendMessage", chat_id=chat, text=message(d, event, mins, st.alert_tag), parse_mode="HTML")
            s["msgs"] = [*s.get("msgs", []), (sent or {}).get("message_id")]
        if event:
            print(f"device {d.key} {event} ({span(mins)})", flush=True)
    state_f.write_text(json.dumps(state))
