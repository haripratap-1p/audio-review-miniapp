import html
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

from .config import get_settings
from .telegram import call

WORKERS = (("Gemma", "gemma.pid", "gemma_guard.log"), ("Gemini", "gemini.pid", None), ("LFM3", "lfm.pid", None))
UPLOADER = "Galaxy call uploader"
UPLOADER_STALE = 45 * 60  # the phone touches the heartbeat every 15 min while the uploader runs
UPLOADER_TEXT = {
    False: "⚠️ <b>Galaxy call uploader stopped</b> on the store phone\nNew calls are not reaching us. "
    "It restarts itself within 15 min while Termux runs; if this stays, open Termux on the phone.",
    True: "✅ <b>Galaxy call uploader running again</b> on the store phone",
}


def pid_alive(pidfile: Path) -> bool:
    try:
        os.kill(int(pidfile.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def uploader_up(beat: str) -> bool | None:
    # beat = host:path of the heartbeat file; None = the tower could not be asked
    host, _, path = beat.partition(":")
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, f"stat -c %Y {shlex.quote(path)}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode == 255:
        return None
    return r.returncode == 0 and time.time() - int(r.stdout.strip() or 0) < UPLOADER_STALE


def worker_changes(prev: dict, now_up: dict) -> list:
    # alert only on a change; the first look just records the state
    return [(name, up) for name, up in now_up.items() if name in prev and prev[name] != up]


def check_workers() -> None:
    st = get_settings()
    state_f = st.home / "workers_state.json"
    prev = json.loads(state_f.read_text()) if state_f.exists() else {}
    now_up = {name: pid_alive(st.home / pid) for name, pid, _ in WORKERS}
    if st.calls_on and st.uploader_beat:
        beat = uploader_up(st.uploader_beat)
        if beat is not None or UPLOADER in prev:
            now_up[UPLOADER] = prev[UPLOADER] if beat is None else beat
    for name, up in worker_changes(prev, now_up):
        if name == UPLOADER:
            text = UPLOADER_TEXT[up]
        elif up:
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
