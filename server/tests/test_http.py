import json

from conftest import COST_CHAT

from review_app import viewer
from review_app.config import SYSTEMS, Settings

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
    assert code == 200 and body["role"] == "tech" and body["is_owner"] and tuple(body["labels"]) == SYSTEMS
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
        409,
        {"error": "This result isn't ready"},
    )
    assert api("/api/review", 5, body={"id": a, "system": "gemma", "verdict": "ok"})[0] == 403
    assert api("/api/review", 5, body={"id": "nope", "system": "pipeline", "verdict": "ok"})[0] == 400
    code, body = api("/api/review", 5, body={"id": a, "system": "pipeline", "verdict": "ok"})
    assert code == 200 and body["votes"]["pipeline"]["mine"] == "ok" and set(body) == {"votes", "lines"}
