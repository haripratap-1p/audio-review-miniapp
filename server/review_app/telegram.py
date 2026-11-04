import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from typing import Any

from .config import get_settings


def check_init_data(init: str, token: str, max_age: int = 86400) -> dict | None:
    # https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    pairs = dict(urllib.parse.parse_qsl(init, keep_blank_values=True))
    got = pairs.pop("hash", "")
    if not got or not token:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), got):
        return None
    if time.time() - int(pairs.get("auth_date", "0")) > max_age:
        return None
    u = json.loads(pairs.get("user", "{}")) or None
    if u:
        u["_sp"] = pairs.get("start_param", "")  # signed by Telegram: which launch link opened the app
    return u


def mode(start_param: str) -> str:
    # <sub>__<conv>__cost opens the cost group's full view; anything else is the client view
    parts = start_param.split("__")
    return "cost" if len(parts) > 2 and parts[2] == "cost" and get_settings().cost_chat else "client"


def tg_api(method: str, _timeout: int = 30, **params: Any) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{get_settings().token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_timeout) as r:
        return json.load(r)
