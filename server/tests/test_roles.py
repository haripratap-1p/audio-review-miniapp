import json

from review_app.config import Settings
from review_app.roles import roles, set_tech


def test_roles_flow(settings: Settings) -> None:
    assert roles() == {"owner": None, "tech": []}  # no roles file yet: everyone General
    settings.roles_file.write_text(json.dumps({"owner": 1, "tech": []}))
    set_tech(7, True)
    assert roles() == {"owner": 1, "tech": [7]}
    set_tech(7, False)
    assert roles() == {"owner": 1, "tech": []}
