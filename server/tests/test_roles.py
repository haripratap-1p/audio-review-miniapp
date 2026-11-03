import json

from review_app.config import SYSTEMS, Settings
from review_app.roles import is_tech, roles, set_tech, systems_for


def test_roles_flow(settings: Settings) -> None:
    assert systems_for(7) == ("pipeline",) and not is_tech(7)  # no roles file yet: everyone General
    settings.roles_file.write_text(json.dumps({"owner": 1, "tech": []}))
    assert systems_for(1) == SYSTEMS and systems_for(7) == ("pipeline",)
    set_tech(7, True)
    assert is_tech(7) and roles() == {"owner": 1, "tech": [7]}
    set_tech(7, False)
    assert not is_tech(7) and is_tech(1)
