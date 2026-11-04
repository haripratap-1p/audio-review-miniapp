from collections.abc import Callable

from conftest import TOKEN, sign

from review_app.telegram import check_init_data, mode


def test_check_init_data(fields: dict) -> None:
    good = sign(fields)
    assert check_init_data(good, TOKEN)["id"] == 7
    assert check_init_data(good, "123:other") is None
    assert check_init_data(good.replace("Asha", "Mallory"), TOKEN) is None
    assert check_init_data(good, TOKEN, max_age=-1) is None


def test_mode_with_cost_group(fields: dict, set_env: Callable) -> None:
    set_env(TG_COST_CHAT="-100")
    assert [mode(s) for s in ("sub", "sub__abc", "sub____cost", "sub__abc__cost", "sub__abc__costly")] == [
        "client",
        "client",
        "cost",
        "cost",
        "client",
    ]
    signed = sign({**fields, "start_param": "sub____cost"})
    assert mode(check_init_data(signed, TOKEN)["_sp"]) == "cost"
    assert check_init_data(signed.replace("sub____cost", "sub____costx"), TOKEN) is None  # can't edit a signed link


def test_mode_without_cost_group() -> None:
    assert mode("sub____cost") == "client"  # no cost group configured: never the full view
