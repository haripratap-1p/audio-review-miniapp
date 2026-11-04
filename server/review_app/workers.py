import html
import json
import os
import time
from pathlib import Path

from .config import get_settings
from .telegram import call

WORKERS = (("Gemma", "gemma.pid", "gemma_guard.log"), ("Gemini", "gemini.pid", None), ("LFM3", "lfm.pid", None))


def pid_alive(pidfile: Path) -> bool:
    try:
        os.kill(int(pidfile.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def worker_changes(prev: dict, now_up: dict) -> list:
    # alert only on a change; the first look just records the state
    return [(name, up) for name, up in now_up.items() if name in prev and prev[name] != up]


def check_workers() -> None:
    st = get_settings()
    state_f = st.home / "workers_state.json"
    prev = json.loads(state_f.read_text()) if state_f.exists() else {}
    now_up = {name: pid_alive(st.home / pid) for name, pid, _ in WORKERS}
    for name, up in worker_changes(prev, now_up):
        if up:
            text = f"✅ <b>{name} running again</b> on thor02"
        else:
            text = f"⚠️ <b>{name} stopped</b> on thor02"
            guard = next((g for n, _, g in WORKERS if n == name and g), None)
            gl = st.home / guard if guard else None
            if gl and gl.exists() and time.time() - gl.stat().st_mtime < 900:
                text += "\nReason: " + html.escape(gl.read_text().strip().splitlines()[-1][:200])
        if st.cost_chat:
            call("sendMessage", chat_id=st.cost_chat, text=text, parse_mode="HTML")
        print(f"worker {name} {'up' if up else 'down'}", flush=True)
    state_f.write_text(json.dumps(now_up))
