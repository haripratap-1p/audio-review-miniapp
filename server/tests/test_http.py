import json

from conftest import COST_CHAT

from review_app import viewer
from review_app.config import SCORED, Settings
from review_app.store import db

COST = "sub____cost"


def owner_is(settings: Settings, uid: int, tech: list | None = None) -> None:
    settings.roles_file.write_text(json.dumps({"owner": uid, "tech": tech or []}))


def test_client_user_sees_pipeline_only(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 1)
    code, body = api("/api/conversations", 5)
    assert code == 200 and body["role"] == "general" and not body["is_owner"] and list(body["labels"]) == ["pipeline"]
    assert api("/api/benchmark", 5)[0] == 403 and api("/api/team", 5)[0] == 403
    assert set(api(f"/api/conversation/{galaxy['a']}", 5)[1]["votes"]) == {"pipeline"}


def test_bad_init_data_and_non_member(api, galaxy: dict) -> None:
    assert api("/api/conversations", 5, tamper=True) == (401, {"error": "session expired"})
    assert api("/api/conversations", 50)[0] == 403  # in neither group
    assert api("/api/conversations", 5, COST) == (403, {"error": "not a group member"})  # cost launcher, not a member


def test_owner_from_client_launcher_gets_full_view_and_team(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 1)
    code, body = api("/api/conversations", 1)
    assert code == 200 and body["role"] == "tech" and body["is_owner"] and tuple(body["labels"]) == SCORED
    assert api("/api/benchmark", 1)[0] == 200 and api("/api/team", 1)[0] == 200


def test_tech_user_from_client_launcher_gets_full_view(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 1, tech=[5])
    code, body = api("/api/conversations", 5)
    assert body["role"] == "tech" and not body["is_owner"] and api("/api/benchmark", 5)[0] == 200
    assert api("/api/team", 5)[0] == 403


def test_cost_member_full_view_without_team(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 1)
    code, body = api("/api/conversations", 20, COST)
    assert code == 200 and body["role"] == "tech" and not body["is_owner"]
    assert api("/api/benchmark", 20, COST)[0] == 200 and api("/api/team", 20, COST)[0] == 403
    assert api("/api/conversations", 20)[0] == 403  # cost member outside the client group, client launcher


def test_owner_team_page_from_cost_launcher(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 21)
    assert api("/api/team", 21, COST)[0] == 200


def test_team_access_labels_and_tech_toggle(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 1, tech=[2])
    viewer.membership.chats[COST_CHAT].add(3)  # 3 is in both groups
    for uid in (1, 2, 3, 4):
        api("/api/conversations", uid)
    people = {p["id"]: p for p in api("/api/team", 1)[1]["people"]}
    assert {u: p["access"] for u, p in people.items()} == {1: "owner", 2: "tech", 3: "cost", 4: "general"}
    assert people[2]["tech"] and not people[4]["tech"]
    assert api("/api/benchmark", 4)[0] == 403
    code, body = api("/api/team", 1, body={"id": 4, "tech": True})
    assert code == 200 and {p["id"]: p["access"] for p in body["people"]}[4] == "tech"
    assert api("/api/conversations", 4)[1]["role"] == "tech" and api("/api/benchmark", 4)[0] == 200
    assert api("/api/team", 2, body={"id": 4, "tech": False})[0] == 403  # only the owner toggles


def test_vote_routes(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 1)
    a = galaxy["a"]
    assert api("/api/review", 20, COST, body={"id": a, "system": "gemini", "verdict": "ok"}) == (
        400,
        {"error": "bad request"},
    )
    assert api("/api/review", 20, COST, body={"id": galaxy["b"], "system": "lfm", "verdict": "ok"}) == (
        409,
        {"error": "This result isn't ready"},
    )
    assert api("/api/review", 5, body={"id": a, "system": "gemma", "verdict": "ok"})[0] == 403
    assert api("/api/review", 5, body={"id": "nope", "system": "pipeline", "verdict": "ok"})[0] == 400
    code, body = api("/api/review", 5, body={"id": a, "system": "pipeline", "verdict": "ok"})
    assert code == 200 and body["votes"]["pipeline"]["mine"] == "ok" and set(body) == {"votes", "lines"}


def test_reference_and_judge_full_view_only(api, galaxy: dict, settings: Settings) -> None:
    owner_is(settings, 1)
    day = settings.results / "Galaxy" / "2026-11-02"
    ref = {"model": "gemini-3.5-flash-lite", "turns": [{"speaker": "Staff", "text": "hi"}]}
    (day / "919800000001_20261102-101500.gemini.json").write_text(json.dumps(ref))
    with db() as c:
        c.execute(
            "INSERT INTO judge_runs VALUES (?,?,?,?,?,?,?,?,?)", (galaxy["a"], "gemma", 0.5, "r", "m", 1, 1, 0, "t")
        )
        c.execute("INSERT INTO judge_lines VALUES (?,?,?,?)", (galaxy["a"], "gemma", 0, "partly"))
    code, full = api(f"/api/conversation/{galaxy['a']}", 20, COST)
    assert code == 200 and "gemini" not in full and set(full["votes"]) == set(SCORED)
    assert full["reference"]["label"] == "Reference (Gemini)" and full["reference"]["turns"] == ref["turns"]
    assert full["reference"]["model"] == "gemini-3.5-flash-lite"
    assert full["judge"] == {"gemma": {"score": 0.5, "ref_model": "r", "lines": {"0": "partly"}}}
    code, client = api(f"/api/conversation/{galaxy['a']}", 5)
    text = json.dumps(client)
    assert code == 200 and not any(w in text for w in ("judge", "reference", "gemini", "partly")), text
    assert "gemini" not in json.dumps(api("/api/conversations", 5)[1])
    code, bm = api("/api/benchmark", 20, COST)
    assert code == 200 and list(bm["systems"]) == list(SCORED) and list(bm["labels"]) == list(SCORED)
    assert bm["systems"]["gemma"]["ai"] == {"judged": 1, "pct": 50}
    assert bm["systems"]["gemma"]["all"] == {"available": 2, "checked": 1, "correct": 1, "pct": 100}
    assert bm["agreement"]["all"] == {"pairs": 1, "pct": 0} and bm["agreement"]["pipeline"]["pairs"] == 0
    assert bm["reference"] == {"label": "Reference (Gemini)", "models": ["gemini-3.5-flash-lite"]}


def test_audio_streams_by_signed_link_with_ranges(api, galaxy: dict, monkeypatch) -> None:
    import time
    import urllib.error
    import urllib.request

    from review_app import http

    day = galaxy["results"] / "Galaxy" / "2026-11-02"
    (day / "audio").mkdir()
    (day / "audio" / "919800000001_20261102-101500.m4a").write_bytes(b"0123456789")
    link = api(f"/api/conversation/{galaxy['a']}", 5)[1]["audio"]

    def get(path: str, rng: str = "") -> tuple:
        req = urllib.request.Request(f"http://127.0.0.1:{api.port}{path}", headers={"Range": rng} if rng else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers.get("Content-Range"), r.headers.get("Accept-Ranges")
        except urllib.error.HTTPError as e:
            return e.code, e.read(), None, None

    assert get(link) == (200, b"0123456789", None, "bytes")  # no X-Init-Data needed
    assert get(link, "bytes=2-4")[:3] == (206, b"234", "bytes 2-4/10")
    assert get(link, "bytes=7-")[:3] == (206, b"789", "bytes 7-9/10")
    assert get(link, "bytes=-2")[:3] == (206, b"89", "bytes 8-9/10")  # player reads the index at the end first
    assert get(link, "bytes=20-")[0] == 416
    assert get(link.replace(galaxy["a"], galaxy["b"]))[0] == 403  # a link opens only its own recording
    assert get(f"/api/audio/{galaxy['a']}")[0] == 403
    monkeypatch.setattr(time, "time", lambda: 2e9)  # 2033: the link has expired
    assert get(link)[0] == 403 and http.AUDIO_TTL == 6 * 3600
