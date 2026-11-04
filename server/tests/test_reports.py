import json

from review_app.config import SCORED
from review_app.conversations import scan, vote
from review_app.reports import benchmark, eod_text
from review_app.store import all_rows, db, judged
from review_app.viewer import Viewer


def test_eod_text_main_group(galaxy: dict) -> None:
    rows = all_rows()
    t = eod_text(scan(rows), rows, "2026-11-02")  # main group: audio pipeline only
    assert "Audio pipeline: checked 2 of 3, 50% correct" in t and "2 votes by 1" in t, t
    assert "Gemma" not in t and "Gemini" not in t and "Best so far" not in t and "clear speech" not in t, t
    assert "1 conversation(s) still to review" in t, t


def test_eod_text_cost_group(galaxy: dict) -> None:
    rows = all_rows()
    bt = eod_text(scan(rows), rows, "2026-11-02", SCORED, "Benchmark", judged())  # cost group: every scored system
    assert "Gemma 4 12B: checked 1 of 2, 100% correct" in bt and "Gemini" not in bt.split("Reference")[0], bt
    assert "Best so far: <b>Gemma 4 12B</b>" in bt and "Asha on Gemma 4 12B: clear speech" in bt and "3 votes" in bt, bt
    assert "Gemma 4 12B AI judge: - (0 judged)" in bt and "AI judge agrees with people: - (0)" in bt, bt
    assert "Reference (Gemini): not scored, model not known" in bt, bt


def test_eod_ai_judge_lines(galaxy: dict) -> None:
    day = galaxy["results"] / "Galaxy" / "2026-11-02"
    ref = json.dumps({"model": "gemini-3.5-flash-lite", "turns": [{"text": "hi"}]})
    (day / "919800000001_20261102-101500.gemini.json").write_text(ref)
    with db() as c:  # a: pipeline ok by people, judge 0.9 (agrees); gemma ok by people, judge 0.5 (disagrees)
        for row in ((galaxy["a"], "pipeline", 0.9), (galaxy["a"], "gemma", 0.5), (galaxy["b"], "gemma", 1.0)):
            c.execute("INSERT INTO judge_runs VALUES (?,?,?,?,?,?,?,?,?)", (*row, "r", "m", 1, 1, 0, "t"))
    rows = all_rows()
    bt = eod_text(scan(rows), rows, "2026-11-02", SCORED, "Benchmark", judged())
    assert "Gemma 4 12B: checked 1 of 2, 100% correct" in bt and "Gemma 4 12B AI judge: 75% (2 judged)" in bt, bt
    assert "Audio pipeline AI judge: 90% (1 judged)" in bt and "AI judge agrees with people: 50% (2)" in bt, bt
    assert "Reference (Gemini): not scored, model gemini-3.5-flash-lite" in bt, bt
    assert "AI judge" not in eod_text(scan(rows), rows, "2026-11-02"), "client EOD stays people-only"


def test_benchmark(galaxy: dict) -> None:
    rows = all_rows()
    bm = benchmark(scan(rows), rows, "2026-11-02")
    assert bm["systems"]["pipeline"]["all"] == {"available": 3, "checked": 2, "correct": 1, "pct": 50}, bm
    assert bm["systems"]["pipeline"]["in-store"]["checked"] == 0 and bm["systems"]["gemma"]["call"]["pct"] == 100
    assert bm["days"] == [{"date": "2026-11-02", "pipeline": 50, "gemma": 100, "lfm": None}], bm["days"]
    assert bm["systems"]["gemma"]["ai"] == {"judged": 0, "pct": None} and "gemini" not in bm["systems"]
    assert bm["agreement"]["all"] == {"pairs": 0, "pct": None}
    assert bm["reference"] == {"label": "Reference (Gemini)", "models": []}
    assert bm["reviewers"] == [{"name": "Asha", "today": 3, "total": 3}], bm["reviewers"]


def test_pipeline_score_ignores_team_votes(galaxy: dict) -> None:
    team = Viewer(99, "Ravi", "Ravi", full=True, owner=False)
    vote(team, galaxy["b"], "pipeline", "ok")  # b: legacy bad + team ok; the pipeline stays at 50%
    vote(team, galaxy["a"], "gemma", "bad")  # other systems count every vote: Gemma 1 ok + 1 bad, tie -> latest
    rows = all_rows()
    bm = benchmark(scan(rows), rows, "2026-11-02")
    assert bm["systems"]["pipeline"]["all"] == {"available": 3, "checked": 2, "correct": 1, "pct": 50}, bm
    assert bm["systems"]["gemma"]["all"]["correct"] == 0
    vote(team, galaxy["b"], "pipeline", "clear")
    vote(team, galaxy["b"], "pipeline", "ok")
    assert "Audio pipeline: checked 2 of 3, 50% correct" in eod_text(scan(), all_rows(), "2026-11-02")
