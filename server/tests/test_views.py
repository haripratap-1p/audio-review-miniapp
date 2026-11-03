import json

from review_app.results import collect
from review_app.store import all_rows, db
from review_app.views import clean_lines, detail, light, line_info, overview, rate_ok


def test_light_rows(galaxy: dict) -> None:
    items = collect(all_rows(), uid=1)
    row = light(items[1])  # b (11:15): Asha voted pipeline only
    assert (
        row["mine"] == {"pipeline": "bad", "gemma": None, "gemini": None, "lfm": None} and row["team"]["gemma"] is None
    )
    assert row["avail"] == {"pipeline": True, "gemma": True, "gemini": False, "lfm": False}
    assert row["ready"] and row["na"] == []
    assert light(items[0])["na"] == ["lfm"] and light(items[0], ("pipeline",))["na"] == []  # General never sees it
    assert light(items[2])["avail"]["lfm"] is True
    gen = light(items[1], ("pipeline",))  # General user: pipeline only
    assert gen["avail"] == {"pipeline": True} and gen["mine"] == {"pipeline": "bad"} and not gen["ready"]
    assert "turns" not in json.dumps(row)


def test_detail_hides_team_votes(galaxy: dict) -> None:
    rows = all_rows()
    gd = detail(collect(rows, uid=1)[1], ("pipeline",))
    assert "gemma" not in gd and "gemini" not in gd and set(gd["votes"]) == {"pipeline"}, gd.keys()
    other = detail(collect(rows, uid=99)[2])  # a (10:15), seen by someone who hasn't voted: no team votes
    assert other["votes"]["gemma"]["ok"] is None and other["votes"]["gemma"]["notes"] == [] and "_js" not in other
    assert other["gemini"] is None
    assert detail(collect(rows, uid=1)[2])["votes"]["gemma"]["notes"] == ["Asha: clear speech"]


def test_overview(galaxy: dict) -> None:
    rows = all_rows()
    assert overview(collect(rows, uid=1), rows, 1, "2026-11-02") == {
        "total": 3,
        "ready": 2,
        "team_pipeline": 2,
        "team_done": 0,
        "my_today": 2,
    }


def test_rate_ok() -> None:
    assert all(rate_ok(5, limit=3) for _ in range(3)) and not rate_ok(5, limit=3)


def test_clean_lines_bounds() -> None:
    assert clean_lines(None, 1) == {} and clean_lines({"0": {"verdict": "ok"}}, 1) == {0: ("ok", "")}
    assert clean_lines({"1": {"verdict": "ok"}}, 1) is None and clean_lines({"-1": {"verdict": "ok"}}, 5) is None
    assert clean_lines({"0": {"verdict": "maybe"}}, 1) is None and clean_lines(["0"], 1) is None


def test_line_info(galaxy: dict) -> None:
    # saved per user, team counts only in the full view after my own vote
    a = galaxy["a"]
    with db() as c:
        c.execute(
            "INSERT INTO line_reviews VALUES (?,?,?,?,?,?,?,?)", (a, "pipeline", 0, 1, "Asha", "bad", "name", "t")
        )
    li = line_info(a, 1, ("pipeline",), {"pipeline": "ok"}, True)
    assert li == {
        "pipeline": {"mine": {"0": {"verdict": "bad", "note": "name"}}, "team": {"0": {"ok": 0, "bad": 1}}}
    }, li
    assert line_info(a, 99, ("pipeline",), {"pipeline": None}, True)["pipeline"] == {"mine": {}, "team": {}}
    assert line_info(a, 1, ("pipeline",), {"pipeline": "ok"}, False)["pipeline"]["team"] == {}
