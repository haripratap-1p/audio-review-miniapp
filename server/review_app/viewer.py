import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .config import IST, MEMBER_OK, SYSTEMS, get_settings
from .roles import roles, team_list
from .store import db
from .telegram import check_init_data, mode, tg_api


class Membership(Protocol):
    def is_member(self, uid: int, chat: str) -> bool: ...


class TelegramMembership:
    def __init__(self) -> None:
        self._seen: dict = {}  # (chat, user_id) -> (is_member, checked_at)

    def is_member(self, uid: int, chat: str) -> bool:
        ok, at = self._seen.get((chat, uid), (False, 0))
        if time.time() - at > 3600:
            try:
                ok = tg_api("getChatMember", chat_id=chat, user_id=uid)["result"]["status"] in MEMBER_OK
            except Exception:
                ok = False
            self._seen[(chat, uid)] = (ok, time.time())
        return ok


membership: Membership = TelegramMembership()


class Denied(Exception):
    def __init__(self, status: int, error: str) -> None:
        super().__init__(error)
        self.status = status


@dataclass(frozen=True)
class Viewer:
    uid: int
    first_name: str
    name: str
    full: bool
    owner: bool

    @property
    def systems(self) -> tuple:
        return SYSTEMS if self.full else ("pipeline",)

    @property
    def role(self) -> str:
        return "tech" if self.full else "general"


def _name(u: dict) -> str:
    return " ".join(filter(None, [u.get("first_name"), u.get("last_name")])) or u.get("username") or str(u["id"])


def viewer_from(init_data: str) -> Viewer:
    st = get_settings()
    u = check_init_data(init_data, st.token)
    if not u:
        raise Denied(401, "session expired")
    cost = mode(u.get("_sp", "")) == "cost"
    if not membership.is_member(u["id"], st.cost_chat if cost else st.chat):
        raise Denied(403, "not a group member")
    r = roles()
    owner = u["id"] == r.get("owner")
    v = Viewer(u["id"], u.get("first_name", ""), _name(u)[:80], cost or owner or u["id"] in r.get("tech", []), owner)
    with db() as c:
        c.execute(
            "INSERT INTO visitors VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, "
            "username=excluded.username, last_seen=excluded.last_seen",
            (v.uid, v.name, u.get("username", ""), datetime.now(IST).isoformat(timespec="seconds")),
        )
    return v


def access(p: dict) -> str:
    cost_chat = get_settings().cost_chat
    if p["owner"]:
        return "owner"
    if p["tech"]:
        return "tech"
    return "cost" if cost_chat and membership.is_member(p["id"], cost_chat) else "general"


def team() -> list:
    return [{**p, "access": access(p)} for p in team_list()]
