import html
import json
import subprocess
import sys
import time
from pathlib import Path

from .config import STEM, get_settings
from .conversations import audio_for, conv_id, kind_of
from .launcher import tunnel_sub
from .telegram import call, launch_url

EMOJI = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}


def state_file() -> Path:
    return get_settings().posted_file


def msgids_file() -> Path:
    return get_settings().results.parent / "telegram_msgids.json"  # conversation key -> audio message id


def call_date(stem: str) -> str:
    m = STEM.match(stem)
    return f"{m[2]}-{m[3]}-{m[4]}" if m else ""


def card(store: str, stem: str, d: dict) -> str:
    m = STEM.match(stem)
    if m:
        who, when = (m[1] or "In-store").replace("_", " ").strip(), f"{m[4]}-{m[3]}-{m[2]} {m[5]}:{m[6]}"
    else:
        who, when = stem, d.get("timestamp", "")
    icon = "🏪" if m and not m[1] else "📞"
    s = (d.get("sentiment") or "NEUTRAL").upper()
    return (
        f"{icon} <b>{html.escape(store)}</b> · {html.escape(who)}\n🕒 {when} · ⏱ {d.get('duration', '')}\n"
        f"{EMOJI.get(s, '⚪')} {s}\n\n<b>Summary:</b> {html.escape(d.get('summary') or '-')}"
    )


def mark(posted: set, key: str) -> None:
    posted.add(key)
    state_file().write_text(json.dumps(sorted(posted)))


def post(key: str, js: Path, posted: set) -> None:
    chat = get_settings().chat
    store = js.parent.parent.name
    d = json.loads(js.read_text(encoding="utf-8"))
    convo = d.get("conversation") or ""
    if not convo.strip():
        return  # no speech in this clip, nothing to alert
    # "#card" recorded separately so a failed transcript never resends the audio
    if key + "#card" not in posted:
        audio = audio_for(js)
        text = card(store, js.stem, d)
        if audio:
            msg = call("sendAudio", chat_id=chat, audio=audio, caption=text[:1024], parse_mode="HTML")
        else:
            msg = call("sendMessage", chat_id=chat, text=text, parse_mode="HTML")
        msgids = msgids_file()
        ids = json.loads(msgids.read_text()) if msgids.exists() else {}
        ids[key] = msg.get("message_id")
        msgids.write_text(json.dumps(ids))
        mark(posted, key + "#card")
    btn = review_button(key)  # newest post at the bottom always carries the Review button
    if len(convo) < 3500:
        call("sendMessage", chat_id=chat, text=f"<b>Transcript</b>\n{html.escape(convo)}", parse_mode="HTML", **btn)
    else:
        txt = js.with_suffix(".txt")
        txt.write_text(convo, encoding="utf-8")
        call("sendDocument", chat_id=chat, document=txt, caption="Transcript", **btn)


def review_button(key: str) -> dict:
    # Mini App link; the quick-tunnel host (changes on restart) rides in startapp with the conversation id
    sub = tunnel_sub()
    if not sub:
        return {}
    return {"reply_markup": {"inline_keyboard": [[{"text": "📝 Review", "url": launch_url(sub, conv_id(key))}]]}}


def call_time(stem: str) -> str:
    m = STEM.match(stem)
    return "".join(m.groups()[1:6]) if m else ""  # to the minute, as posted so far


def skip(stem: str) -> bool:
    # before POST_FROM by call date, or its type (CALLS / INSTORE) is switched off
    st = get_settings()
    return call_date(stem) < st.poster_call_date_from or not st.kind_on(kind_of(stem))


def main() -> None:
    st = get_settings()
    if not st.token or not st.chat:
        sys.exit("TG_TOKEN and TG_CHAT must be set")
    state = state_file()
    posted = set(json.loads(state.read_text())) if state.exists() else set()
    while True:
        # sort by call time (filename) so the group reads in order
        for js in sorted(st.results.glob("*/*/*.json"), key=lambda p: call_time(p.stem)):
            if "." in js.stem:  # model outputs (<stem>.<model>.json) stay out of the group
                continue
            key = f"{js.parent.parent.name}/{js.stem}"
            if skip(js.stem):
                continue
            try:
                if key not in posted:
                    post(key, js, posted)
                    mark(posted, key)
                    print(f"posted {key}", flush=True)
                    time.sleep(3)  # stay under Telegram's ~20 msgs/min per group
            except (subprocess.CalledProcessError, OSError, RuntimeError) as e:
                print(f"post failed {key}: {str(e)[:300]}", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
