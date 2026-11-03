import hashlib
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .config import get_settings
from .launcher import tunnel_sub

EMOJI = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}
# call: <number or contact name>_<YYYYMMDD-HHMMSS>; in-store clip: <YYYYMMDD_HHMMSS>
STEM = re.compile(r"(?:(.+?)_+)?(\d{4})(\d\d)(\d\d)[-_](\d\d)(\d\d)\d\d$")


def state_file() -> Path:
    return get_settings().results.parent / "telegram_posted.json"


def msgids_file() -> Path:
    return get_settings().results.parent / "telegram_msgids.json"  # conversation key -> audio message id


def call_date(stem: str) -> str:
    m = STEM.match(stem)
    return f"{m[2]}-{m[3]}-{m[4]}" if m else ""


def form(k: str, v: Any) -> list:
    # Path = file upload; text via --form-string so a leading "<" or "@" is sent literally
    return ["-F", f"{k}=@{v}"] if isinstance(v, Path) else ["--form-string", f"{k}={v}"]


def tg(method: str, **fields: Any) -> dict:
    args = ["curl", "-sS", "--fail-with-body", "-m", "120", "-K", "-"]
    for k, v in fields.items():
        args += form(k, v)
    api = f"https://api.telegram.org/bot{get_settings().token}"
    for _ in range(5):
        try:
            # URL (with token) goes via stdin so it never shows in `ps`
            r = subprocess.run(args, input=f'url = "{api}/{method}"', text=True, check=True, capture_output=True)
            return json.loads(r.stdout).get("result") or {}
        except subprocess.CalledProcessError as e:
            m = re.search(r'"retry_after":(\d+)', e.stdout or "")
            if not m:
                raise
            time.sleep(int(m[1]) + 1)
    raise RuntimeError(f"{method}: still rate-limited")


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
        audio = next(js.parent.joinpath("audio").glob(js.stem + ".*"), None)
        if audio and audio.suffix == ".mp4":
            # in-store clips are CCTV video; post only the sound
            m4a = js.with_suffix(".m4a")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-vn", "-c:a", "copy", str(m4a)]
            subprocess.run(cmd, check=True)
            audio = m4a
        text = card(store, js.stem, d)
        if audio:
            msg = tg("sendAudio", chat_id=chat, audio=audio, caption=text[:1024], parse_mode="HTML")
        else:
            msg = tg("sendMessage", chat_id=chat, text=text, parse_mode="HTML")
        msgids = msgids_file()
        ids = json.loads(msgids.read_text()) if msgids.exists() else {}
        ids[key] = msg.get("message_id")
        msgids.write_text(json.dumps(ids))
        mark(posted, key + "#card")
    btn = review_button(key)  # newest post at the bottom always carries the Review button
    if len(convo) < 3500:
        tg("sendMessage", chat_id=chat, text=f"<b>Transcript</b>\n{html.escape(convo)}", parse_mode="HTML", **btn)
    else:
        txt = js.with_suffix(".txt")
        txt.write_text(convo, encoding="utf-8")
        tg("sendDocument", chat_id=chat, document=txt, caption="Transcript", **btn)


def review_button(key: str) -> dict:
    # Mini App link; the quick-tunnel host (changes on restart) rides in startapp with the conversation id
    sub = tunnel_sub()
    if not sub:
        return {}
    url = f"{get_settings().app_link}?startapp={sub}__{hashlib.sha1(key.encode()).hexdigest()[:10]}"
    return {"reply_markup": json.dumps({"inline_keyboard": [[{"text": "📝 Review", "url": url}]]})}


def call_time(stem: str) -> str:
    m = STEM.match(stem)
    return "".join(m.groups()[1:]) if m else ""


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
            if call_date(js.stem) < st.poster_post_from:
                continue
            try:
                if key not in posted:
                    post(key, js, posted)
                    mark(posted, key)
                    print(f"posted {key}", flush=True)
                    time.sleep(3)  # stay under Telegram's ~20 msgs/min per group
            except (subprocess.CalledProcessError, RuntimeError) as e:
                err = getattr(e, "stdout", "") or getattr(e, "stderr", "") or str(e)
                print(f"post failed {key}: {err[:300]}", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
