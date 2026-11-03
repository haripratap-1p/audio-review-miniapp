from review_app.config import SYSTEMS
from review_app.reports import benchmark, eod_text
from review_app.results import collect
from review_app.store import all_rows


def test_eod_text_main_group(galaxy: dict) -> None:
    rows = all_rows()
    t = eod_text(collect(rows, uid=1), rows, "2026-11-02")  # main group: audio pipeline only
    assert "Audio pipeline: checked 2 of 3, 50% correct" in t and "2 votes by 1" in t, t
    assert "Gemma" not in t and "Gemini" not in t and "Best so far" not in t and "clear speech" not in t, t
    assert "1 conversation(s) still to review" in t, t


def test_eod_text_cost_group(galaxy: dict) -> None:
    rows = all_rows()
    bt = eod_text(collect(rows, uid=1), rows, "2026-11-02", SYSTEMS, "Benchmark")  # cost group: everything
    assert "Gemma 4 12B: checked 1 of 2, 100% correct" in bt and "Gemini 3.6 Flash: checked 0 of 0, - correct" in bt, bt
    assert "Best so far: <b>Gemma 4 12B</b>" in bt and "Asha on Gemma 4 12B: clear speech" in bt and "3 votes" in bt, bt


def test_benchmark(galaxy: dict) -> None:
    rows = all_rows()
    bm = benchmark(collect(rows, uid=1), rows, "2026-11-02")
    assert bm["systems"]["pipeline"]["all"] == {"available": 3, "checked": 2, "correct": 1, "pct": 50}, bm
    assert bm["systems"]["pipeline"]["in-store"]["checked"] == 0 and bm["systems"]["gemma"]["call"]["pct"] == 100
    assert bm["days"] == [{"date": "2026-11-02", "pipeline": 50, "gemma": 100, "gemini": None, "lfm": None}], bm["days"]
    assert bm["reviewers"] == [{"name": "Asha", "today": 3, "total": 3}], bm["reviewers"]
