import json
import os
import time

from review_app.results import collect, pipeline_turns, verdict
from review_app.store import all_rows


def test_verdict() -> None:
    assert verdict([{"verdict": "ok", "ts": "1"}, {"verdict": "bad", "ts": "2"}]) == "bad"
    assert verdict([{"verdict": "ok", "ts": "1"}, {"verdict": "ok", "ts": "2"}, {"verdict": "bad", "ts": "3"}]) == "ok"


def test_pipeline_turns() -> None:
    assert pipeline_turns("[Speaker_01]: Hello {Hi}\n[Speaker_02]: Yes")[1] == {"speaker": "Speaker 2", "text": "Yes"}


def test_collect_kinds_and_mine(galaxy: dict) -> None:
    items = collect(all_rows(), uid=1)
    assert [i["kind"] for i in items] == ["in-store", "call", "call"] and items[1]["votes"]["pipeline"]["mine"] == "bad"


def test_arrival_order_and_folder_date_filter(galaxy: dict) -> None:
    # newest arrival first, whatever the phone's call date; the folder date gates POST_FROM
    res = galaxy["results"]
    old = res / "Galaxy" / "2026-11-03"
    old.mkdir()
    (old / "919800000003_20260622-090000.json").write_text(json.dumps({"conversation": "[Speaker_01]: hi"}))
    os.utime(old / "919800000003_20260622-090000.json", (time.time() + 60, time.time() + 60))  # arrived last
    (res / "Galaxy" / "2026-10-01").mkdir()
    early = res / "Galaxy" / "2026-10-01" / "919800000004_20261001-090000.json"
    early.write_text(json.dumps({"conversation": "[Speaker_01]: x"}))
    got = collect([])
    assert got[0]["key"] == "Galaxy/919800000003_20260622-090000" and len(got) == 4, [i["key"] for i in got]
