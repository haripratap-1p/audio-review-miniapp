import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from review_app import conversations
from review_app.conversations import NotAllowed, NotReady, Rejected, get, listing, recording, scan, vote
from review_app.store import db
from review_app.viewer import Viewer

ASHA = Viewer(1, "Asha", "Asha", full=True, owner=False)
ASHA_CLIENT = Viewer(1, "Asha", "Asha", full=False, owner=False)
OTHER = Viewer(99, "Ravi", "Ravi", full=True, owner=False)


def test_listing_rows_per_viewer(galaxy: dict) -> None:
    out = listing(ASHA, today="2026-11-02")
    c, b, a = out["items"]  # newest call time first
    assert b["mine"] == {"pipeline": "bad", "gemma": None, "gemini": None, "lfm": None} and b["team"]["gemma"] is None
    assert b["avail"] == {"pipeline": True, "gemma": True, "gemini": False, "lfm": False} and b["ready"]
    assert c["na"] == ["lfm"] and c["avail"]["lfm"] is False and a["avail"]["lfm"] is True
    assert "turns" not in json.dumps(out)
    assert {k: out[k] for k in ("total", "ready", "team_pipeline", "team_done", "my_today")} == {
        "total": 3,
        "ready": 2,
        "team_pipeline": 2,
        "team_done": 0,
        "my_today": 2,
    }
    gen = listing(ASHA_CLIENT)["items"][1]  # client view: pipeline only, never the N/A badge
    assert gen["avail"] == {"pipeline": True} and gen["mine"] == {"pipeline": "bad"} and not gen["ready"]
    assert listing(ASHA_CLIENT)["items"][0]["na"] == []


def test_get_hides_team_votes_until_i_voted(galaxy: dict) -> None:
    gd = get(galaxy["b"], ASHA_CLIENT)
    assert "gemma" not in gd and set(gd["votes"]) == {"pipeline"} and list(gd["lines"]) == ["pipeline"]
    other = get(galaxy["a"], OTHER)
    assert other["votes"]["gemma"]["ok"] is None and other["votes"]["gemma"]["notes"] == [] and other["gemini"] is None
    assert get(galaxy["a"], ASHA)["votes"]["gemma"]["notes"] == ["Asha: clear speech"]
    assert get("nope", ASHA) is None


def test_vote_lines_and_undo(galaxy: dict) -> None:
    a = galaxy["a"]
    out = vote(OTHER, a, "pipeline", "bad", "name wrong", {"0": {"verdict": "bad", "note": "name"}})
    assert out["votes"]["pipeline"]["bad"] == 1 and out["votes"]["pipeline"]["notes"] == ["Ravi: name wrong"]
    assert out["lines"]["pipeline"] == {
        "mine": {"0": {"verdict": "bad", "note": "name"}},
        "team": {"0": {"ok": 0, "bad": 1}},
    }
    assert vote(ASHA_CLIENT, a, "pipeline", "ok")["lines"]["pipeline"]["team"] == {}  # client view: no team line counts
    out = vote(OTHER, a, "pipeline", "clear")
    assert out["votes"]["pipeline"]["mine"] is None and out["lines"]["pipeline"]["mine"] == {}
    with db() as c:
        assert c.execute("SELECT count(*) FROM line_reviews WHERE conv=?", (a,)).fetchone()[0] == 0


def test_vote_records_source(galaxy: dict) -> None:
    vote(OTHER, galaxy["a"], "pipeline", "ok")
    vote(Viewer(5, "Sam", "Sam", full=False, owner=False), galaxy["a"], "pipeline", "bad")
    with db() as c:
        got = dict(c.execute("SELECT user_id, source FROM reviews WHERE conv=? AND system='pipeline'", (galaxy["a"],)))
    assert got == {1: None, 99: "team", 5: "analysis"}


def test_vote_rejections(galaxy: dict, settings) -> None:
    a = galaxy["a"]
    with pytest.raises(NotReady, match="This result isn't ready"):
        vote(ASHA, a, "gemini", "ok")  # no Gemini result yet
    day = settings.results / "Galaxy" / "2026-11-02"
    (day / "919800000001_20261102-101500.gemini.json").write_text(json.dumps({"error": "quota", "turns": []}))
    with pytest.raises(NotReady):
        vote(ASHA, a, "gemini", "bad")  # errored result
    with pytest.raises(NotAllowed):
        vote(ASHA_CLIENT, a, "gemma", "ok")
    for args in (("nope", "pipeline", "ok"), (a, "x", "ok"), (a, "pipeline", "maybe")):
        with pytest.raises(Rejected, match="bad request"):
            vote(ASHA, *args)
    for lines in ({"1": {"verdict": "ok"}}, {"-1": {"verdict": "ok"}}, {"0": {"verdict": "maybe"}}, ["0"]):
        with pytest.raises(Rejected, match="bad line marks"):
            vote(ASHA, a, "pipeline", "ok", "", lines)


def test_pipeline_scored_on_analysis_votes_only(galaxy: dict) -> None:
    vote(OTHER, galaxy["b"], "pipeline", "ok")  # Tech team says ok, analysis (and legacy) said bad
    vote(Viewer(5, "Sam", "Sam", full=False, owner=False), galaxy["b"], "pipeline", "ok")
    b = next(c for c in scan() if c.id == galaxy["b"])
    assert b.verdict("pipeline") == "ok" and b.scored("pipeline") == "ok"
    vote(Viewer(5, "Sam", "Sam", full=False, owner=False), galaxy["b"], "pipeline", "bad")
    b = next(c for c in scan() if c.id == galaxy["b"])
    assert b.verdict("pipeline") == "bad" and b.scored("pipeline") == "bad"  # 2 analysis bad vs the team's ok
    vote(Viewer(6, "Tej", "Tej", full=True, owner=False), galaxy["b"], "pipeline", "ok")
    b = next(c for c in scan() if c.id == galaxy["b"])
    assert b.verdict("pipeline") == "ok" and b.scored("pipeline") == "bad"


def test_scan_order_and_folder_date_filter(galaxy: dict) -> None:
    # newest arrival first, whatever the phone's call date; the folder date gates POST_FROM
    res = galaxy["results"]
    late = res / "Galaxy" / "2026-11-03"
    late.mkdir()
    (late / "919800000003_20260622-090000.json").write_text(json.dumps({"conversation": "[Speaker_01]: hi"}))
    os.utime(late / "919800000003_20260622-090000.json", (time.time() + 60, time.time() + 60))  # arrived last
    (res / "Galaxy" / "2026-10-01").mkdir()
    early = res / "Galaxy" / "2026-10-01" / "919800000004_20261001-090000.json"
    early.write_text(json.dumps({"conversation": "[Speaker_01]: x"}))
    got = scan([])
    assert got[0].key == "Galaxy/919800000003_20260622-090000" and len(got) == 4, [c.key for c in got]
    assert [c.kind for c in got[1:]] == ["in-store", "call", "call"]
    assert got[0].results["pipeline"]["turns"] == [{"speaker": "Speaker 1", "text": "hi"}]


def test_recording_extracts_sound_once(galaxy: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    day = galaxy["results"] / "Galaxy" / "2026-11-02"
    (day / "audio").mkdir()
    (day / "audio" / "919800000001_20261102-101500.mp3").write_bytes(b"mp3")
    (day / "audio" / "20261102_154507.mp4").write_bytes(b"video")
    runs = []

    def ffmpeg(cmd: list, check: bool) -> None:
        runs.append(cmd)
        assert not (day / "20261102_154507.m4a").exists()  # never visible half-written
        Path(cmd[-1]).write_bytes(b"sound")

    monkeypatch.setattr(subprocess, "run", ffmpeg)
    assert recording(galaxy["a"]).read_bytes() == b"mp3" and recording(galaxy["b"]) is None
    clip = next(c for c in scan([]) if c.kind == "in-store")
    assert recording(clip.id) == day / "20261102_154507.m4a" and recording(clip.id).read_bytes() == b"sound"
    assert len(runs) == 1 and not list(day.glob("*.partial.m4a"))
    assert conversations.recording("nope") is None
