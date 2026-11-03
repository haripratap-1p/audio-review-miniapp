import pytest

from review_app import launcher, reports, scheduler, store, workers


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict:
    state = {"sub": "", "calls": []}

    def pin_launcher() -> None:
        state["calls"].append("pin_launcher")
        raise RuntimeError("boom")

    def pin_cost_launcher() -> None:
        state["calls"].append("pin_cost_launcher")

    def ensure_card() -> None:
        state["calls"].append("ensure_card")

    monkeypatch.setattr(launcher, "tunnel_sub", lambda: state["sub"])
    for f in (pin_launcher, pin_cost_launcher, ensure_card):
        monkeypatch.setattr(launcher, f.__name__, f)
    monkeypatch.setattr(store, "sync_db", lambda: 0)
    monkeypatch.setattr(workers, "check_workers", lambda: None)
    monkeypatch.setattr(reports, "post_eod", lambda dry: None)
    return state


def test_tick_repins_only_when_tunnel_changes(fakes: dict, capsys: pytest.CaptureFixture) -> None:
    fakes["sub"] = "aaa"
    assert scheduler.tick("aaa") == "aaa" and fakes["calls"] == []
    fakes["sub"] = "bbb"
    assert scheduler.tick("aaa") == "bbb"
    assert fakes["calls"] == ["pin_launcher", "pin_cost_launcher", "ensure_card"]
    assert "pin_launcher failed: boom" in capsys.readouterr().out
    fakes["calls"].clear()
    assert scheduler.tick("bbb") == "bbb" and fakes["calls"] == []
    fakes["sub"] = ""  # log empty for a moment: keep pins as they are
    assert scheduler.tick("bbb") == "bbb" and fakes["calls"] == []


def test_tick_pins_once_tunnel_appears(fakes: dict) -> None:
    fakes["sub"] = "ccc"
    assert scheduler.tick("") == "ccc" and fakes["calls"] == ["pin_launcher", "pin_cost_launcher", "ensure_card"]
