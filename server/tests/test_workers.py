import os
from pathlib import Path

from review_app.workers import pid_alive, worker_changes


def test_worker_changes() -> None:
    assert worker_changes({}, {"Gemma": False}) == []  # first look: no alert
    assert worker_changes({"Gemma": True, "Gemini": True}, {"Gemma": False, "Gemini": True}) == [("Gemma", False)]
    assert worker_changes({"Gemma": False}, {"Gemma": False}) == []
    assert worker_changes({"Gemma": False}, {"Gemma": True}) == [("Gemma", True)]


def test_pid_alive(tmp_path: Path) -> None:
    pf = tmp_path / "x.pid"
    pf.write_text(str(os.getpid()))
    assert pid_alive(pf) and not pid_alive(tmp_path / "missing.pid")
