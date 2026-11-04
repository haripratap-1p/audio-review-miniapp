import time
from collections.abc import Callable
from datetime import datetime

from . import devices, launcher, reports, store, workers
from .config import EOD_HOUR, IST, get_settings


def run_steps(*steps: Callable[[], None]) -> None:
    for step in steps:
        try:
            step()
        except Exception as e:
            print(f"{step.__name__} failed: {e}", flush=True)


def repin() -> None:
    run_steps(launcher.pin_launcher, launcher.pin_cost_launcher, launcher.ensure_card)


def tick(last_sub: str) -> str:
    # one scheduler pass; returns the tunnel host the launchers now point at
    sub = launcher.tunnel_sub()
    if sub and sub != last_sub:
        repin()
        last_sub = sub
    try:
        store.sync_db()
    except Exception as e:
        print(f"db sync failed: {e}", flush=True)
    try:
        workers.check_workers()
    except Exception as e:
        print(f"worker check failed: {e}", flush=True)
    try:
        devices.check_devices()
    except Exception as e:
        print(f"device check failed: {e}", flush=True)
    sent = get_settings().home / "review_eod_sent.txt"
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    if now.hour >= EOD_HOUR and (sent.read_text().strip() if sent.exists() else "") != today:
        try:
            reports.post_eod(dry=False)
            sent.write_text(today)
            print(f"EOD posted {today}", flush=True)
        except Exception as e:
            print(f"EOD failed: {e}", flush=True)
    return last_sub


def scheduler() -> None:
    # keeps the pinned launcher pointing at the current tunnel and posts the EOD once a day at 19:00 IST
    for _ in range(12):  # tunnel log may appear a few seconds after start
        if launcher.tunnel_sub():
            break
        time.sleep(5)
    last_sub = launcher.tunnel_sub()
    run_steps(launcher.ensure_owner)
    repin()
    while True:
        last_sub = tick(last_sub)
        time.sleep(60)
