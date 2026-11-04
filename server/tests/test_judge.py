import json

import pytest
from conftest import reply

from review_app import judge
from review_app.conversations import conv_id
from review_app.store import db

A, B, C = "919800000001_20261102-101500", "919800000002_20261102-111500", "20261102_154507"
REF = {"model": "gemini-3.5-flash-lite", "turns": [{"speaker": "Staff", "text": "नमस्ते"}, {"text": "hi there"}]}


def refs(galaxy: dict, *stems: str, ref: dict = REF) -> None:
    day = galaxy["results"] / "Galaxy" / "2026-11-02"
    for stem in stems:
        (day / f"{stem}.gemini.json").write_text(json.dumps(ref))


def judged_pairs() -> list:
    with db() as c:
        return c.execute("SELECT conv, system, score, ref_model, model FROM judge_runs ORDER BY rowid").fetchall()


def test_prompt_has_meaning_only_rules() -> None:
    body = judge.request_body([{"text": "a\nb"}], [{"text": "x"}, {"text": "y"}], "gemini-3.5-flash-lite")
    rules = body["systemInstruction"]["parts"][0]["text"]
    for rule in ("meaning only", "spelling", "script (Devanagari vs Latin)", "transliteration", "word order"):
        assert rule in rules, rule
    assert "filler words" in rules and "punctuation" in rules
    assert body["contents"][0]["parts"][0]["text"] == "REFERENCE:\n- a b\n\nSYSTEM LINES:\n1. x\n2. y"
    gc = body["generationConfig"]
    assert gc["responseMimeType"] == "application/json" and gc["responseSchema"] == judge.SCHEMA
    assert gc["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert judge.thinking("gemini-2.5-flash-lite") == {"thinkingBudget": 0}


def test_parse_and_score() -> None:
    got = judge.parse(
        reply(
            [
                {"line": 1, "meaning": "same"},
                {"line": 1, "meaning": "wrong"},  # duplicate: first wins
                {"line": 2, "meaning": "partly"},
                {"line": 4, "meaning": "same"},  # out of range
                {"line": 3, "meaning": "maybe"},
                {"line": "3", "meaning": "same"},
                "junk",
            ]
        ),
        3,
    )
    assert got == {0: "same", 1: "partly"}  # 1-based from the model, 0-based like the app's line marks
    assert judge.score(got, 3) == 0.5  # line 3 missing counts as not same
    assert judge.parse(reply("not json"), 3) is None and judge.parse({}, 3) is None
    assert judge.parse(reply('{"lines": 5}'), 3) is None and judge.parse(reply("5"), 3) is None


def test_cost_counts_thinking_as_output(set_env) -> None:
    assert judge.usage(reply([], (1000, 100, 50))) == (1000, 150)
    assert judge.cost(1000, 150) == pytest.approx(0.000675)
    set_env(JUDGE_PRICE_IN="1", JUDGE_PRICE_OUT="10")
    assert judge.cost(1_000_000, 1_000_000) == pytest.approx(11.0)


def test_order_cap_and_idempotent(galaxy: dict, gemini, set_env, capsys) -> None:
    set_env(GEMINI_API_KEYS="k1")
    refs(galaxy, A, B, C)
    stats = judge.run(limit=3)
    assert stats["judged"] == 3 and stats["skipped"] == 3
    # unreviewed clip first, then the reviewed calls, newest first
    assert [(cv, s) for cv, s, *_ in judged_pairs()] == [
        (conv_id(f"Galaxy/{C}"), "pipeline"),
        (galaxy["b"], "pipeline"),
        (galaxy["b"], "gemma"),
    ]
    assert len(gemini.calls) == 3 and all(k == "k1" for _, k, _ in gemini.calls)
    assert "judged 3, skipped 3, cost $0.0020" in capsys.readouterr().out
    assert judge.run()["judged"] == 3 and judge.run() == {"judged": 0, "skipped": 0, "cost": 0.0}
    assert len(gemini.calls) == 6 and {r[3] for r in judged_pairs()} == {"gemini-3.5-flash-lite"}
    set_env(GEMINI_API_KEYS="k1", JUDGE_DAILY_CAP="1")
    assert judge.run(limit=5)["judged"] == 0  # nothing left


def test_cap_from_settings(galaxy: dict, gemini, set_env) -> None:
    set_env(GEMINI_API_KEYS="k1", JUDGE_DAILY_CAP="2")
    refs(galaxy, A, B, C)
    assert judge.run(limit=10) == {"judged": 2, "skipped": 4, "cost": pytest.approx(2 * 0.000675)}


def test_lines_stored_zero_based(galaxy: dict, gemini, set_env) -> None:
    set_env(GEMINI_API_KEYS="k1")
    refs(galaxy, A)
    gemini.replies = [(200, reply([{"line": 1, "meaning": "partly"}]))]
    judge.run(limit=1)
    with db() as c:
        assert c.execute("SELECT conv, system, line, meaning FROM judge_lines").fetchall() == [
            (galaxy["a"], "pipeline", 0, "partly")
        ]
        assert c.execute("SELECT score, tokens_in, tokens_out FROM judge_runs").fetchone() == (0.5, 1000, 150)


def test_unusable_reference_skipped(galaxy: dict, gemini, set_env) -> None:
    set_env(GEMINI_API_KEYS="k1")
    refs(galaxy, A, ref={"model": "m", "turns": [], "error": "quota"})
    refs(galaxy, B, ref={"skipped": "language not supported", "turns": [{"text": "x"}]})
    assert judge.run()["judged"] == 0 and gemini.calls == []


def test_key_rotation_on_quota(galaxy: dict, gemini, set_env, capsys) -> None:
    set_env(GEMINI_API_KEYS="k1,k2")
    refs(galaxy, B)
    gemini.replies = [(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})]
    assert judge.run()["judged"] == 2
    assert [k for _, k, _ in gemini.calls] == ["k1", "k2", "k2"]
    out = capsys.readouterr().out
    assert "key 1 of 2 out of quota" in out and "k1" not in out and "k2" not in out


def test_all_keys_out_of_quota_stops(galaxy: dict, gemini, set_env) -> None:
    set_env(GEMINI_API_KEYS="k1,k2")
    refs(galaxy, A, B)
    gemini.replies = [(429, {}), (200, {"error": {"status": "RESOURCE_EXHAUSTED"}})]
    assert judge.run() == {"judged": 0, "skipped": 5, "cost": 0.0}
    assert len(gemini.calls) == 2


def test_failure_logged_without_key_and_retried(galaxy: dict, gemini, set_env, capsys) -> None:
    set_env(GEMINI_API_KEYS="secretkey1")
    refs(galaxy, A)
    gemini.replies = [(500, {"error": {"message": "boom for secretkey1"}}), (200, reply("{broken"))]
    assert judge.run(limit=2) == {"judged": 0, "skipped": 3, "cost": pytest.approx(0.000675)}
    out = capsys.readouterr().out
    assert "judge failed Galaxy/919800000001_20261102-101500 pipeline: HTTP 500 boom for ***" in out
    assert "HTTP 200 unreadable reply" in out and "secretkey1" not in out
    assert judge.run()["judged"] == 3  # retried next run


def test_dry_run_sends_nothing(galaxy: dict, gemini, set_env, capsys) -> None:
    refs(galaxy, A)
    judge.main(["--dry-run", "--limit", "2"])
    out = capsys.readouterr().out
    assert gemini.calls == [] and judged_pairs() == []
    assert "would judge Galaxy/919800000001_20261102-101500 pipeline (1 lines)" in out
    assert "would judge 2, skipped 1, cost $0.0000" in out


def test_no_keys_sends_nothing(galaxy: dict, gemini, capsys) -> None:
    refs(galaxy, A)
    assert judge.run()["skipped"] == 3 and gemini.calls == []
    assert "GEMINI_API_KEYS is not set" in capsys.readouterr().out
