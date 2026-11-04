import json

from .config import get_settings
from .store import db


def roles() -> dict:
    try:
        return json.loads(get_settings().roles_file.read_text())
    except (OSError, ValueError):
        return {"owner": None, "tech": []}


def set_tech(uid: int, on: bool) -> None:
    roles_f = get_settings().roles_file
    r = roles()
    tech = set(r.get("tech", []))
    (tech.add if on else tech.discard)(uid)
    r["tech"] = sorted(tech)
    tmp = roles_f.with_suffix(".tmp")
    tmp.write_text(json.dumps(r))
    tmp.rename(roles_f)


def team_list() -> list:
    r = roles()
    with db() as c:
        rows = c.execute("SELECT user_id, name, username, last_seen FROM visitors ORDER BY last_seen DESC").fetchall()
    return [
        {
            "id": uid,
            "name": n,
            "username": un,
            "last_seen": ls,
            "owner": uid == r.get("owner"),
            "tech": uid == r.get("owner") or uid in r.get("tech", []),
        }
        for uid, n, un, ls in rows
    ]
