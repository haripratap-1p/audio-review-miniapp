import os
import subprocess
import time
from pathlib import Path

import pytest

from review_app import workers
from review_app.workers import UPLOADER, check_workers, pid_alive, worker_changes


def test_uploader_alert_goes_to_cost_group(set_env, tg, monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(TG_COST_CHAT="-100")
    reply = {"rc": 0, "out": str(int(time.time()))}
    fake = lambda *a, **k: subprocess.CompletedProcess(a, reply["rc"], reply["out"], "")  # noqa: E731
    monkeypatch.setattr(workers.subprocess, "run", fake)
    check_workers()  # first look only records
    reply["out"] = str(int(time.time()) - 3600)  # heartbeat 1 h old
    check_workers()
    reply["rc"] = 255  # tower unreachable: no change, no alert
    check_workers()
    reply.update(rc=0, out=str(int(time.time())))
    check_workers()
    sent = [(p["chat_id"], p["text"]) for m, p in tg.calls if m == "sendMessage"]
    assert [c for c, _ in sent] == ["-100", "-100"]
    assert "uploader stopped" in sent[0][1] and "running again" in sent[1][1]
    set_env(CALLS="false")
    check_workers()
    assert UPLOADER not in (workers.get_settings().home / "workers_state.json").read_text()


def test_worker_changes() -> None:
    assert worker_changes({}, {"Gemma": False}) == []  # first look: no alert
    assert worker_changes({"Gemma": True, "Gemini": True}, {"Gemma": False, "Gemini": True}) == [("Gemma", False)]
    assert worker_changes({"Gemma": False}, {"Gemma": False}) == []
    assert worker_changes({"Gemma": False}, {"Gemma": True}) == [("Gemma", True)]


def test_pid_alive(tmp_path: Path) -> None:
    pf = tmp_path / "x.pid"
    pf.write_text(str(os.getpid()))
    assert pid_alive(pf) and not pid_alive(tmp_path / "missing.pid")
