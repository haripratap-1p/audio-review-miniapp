import hashlib
import hmac
import json
import mimetypes
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

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


def build_link(sub: str, conv: str | None = None, cost: bool = False) -> str:
    # startapp grammar: <sub>, <sub>__<conv>, <sub>____cost, <sub>__<conv>__cost
    return f"{sub}__{conv or ''}__cost" if cost else f"{sub}__{conv}" if conv else sub


def parse_link(start_param: str) -> tuple[str, str, bool]:
    parts = start_param.split("__")
    return parts[0], parts[1] if len(parts) > 1 else "", len(parts) > 2 and parts[2] == "cost"


def launch_url(sub: str, conv: str | None = None, cost: bool = False) -> str:
    return f"{get_settings().app_link}?startapp={build_link(sub, conv, cost)}"


def mode(start_param: str) -> str:
    # a cost link opens the cost group's full view only when a cost group is configured
    return "cost" if parse_link(start_param)[2] and get_settings().cost_chat else "client"


class TelegramError(RuntimeError):
    pass


class Client(Protocol):
    def call(self, method: str, **params: Any) -> Any: ...


def multipart(fields: dict) -> tuple[bytes, str]:
    # Path = file upload; str sent literally; anything else as JSON (reply_markup)
    boundary = secrets.token_hex(16)
    parts = []
    for k, v in fields.items():
        if isinstance(v, Path):
            ctype = mimetypes.guess_type(v.name)[0] or "application/octet-stream"
            name = v.name.replace('"', "")
            head, data = f'name="{k}"; filename="{name}"\r\nContent-Type: {ctype}', v.read_bytes()
        else:
            head, data = f'name="{k}"', (v if isinstance(v, str) else json.dumps(v)).encode()
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; {head}\r\n\r\n".encode() + data + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class HttpClient:
    base = "https://api.telegram.org"

    def call(self, method: str, **params: Any) -> Any:
        if any(isinstance(v, Path) for v in params.values()):
            (data, ctype), timeout = multipart(params), 120
        else:
            (data, ctype), timeout = (json.dumps(params).encode(), "application/json"), 30
        req = urllib.request.Request(
            f"{self.base}/bot{get_settings().token}/{method}", data=data, headers={"Content-Type": ctype}
        )
        for _ in range(5):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.load(r).get("result")
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read() or b"{}")
                except ValueError:
                    err = {}
                wait = (err.get("parameters") or {}).get("retry_after")
                if not wait:
                    raise TelegramError(f"{method}: {err.get('description') or e.code}") from None
                time.sleep(int(wait) + 1)
        raise TelegramError(f"{method}: still rate-limited")


client: Client = HttpClient()


def call(method: str, **params: Any) -> Any:
    return client.call(method, **params)


def keep_pinned(chat: str, state_name: str, text: str, markup: dict | None = None, parse_mode: str = "") -> int:
    # one message kept pinned: edit it in place (its button, else its text); post a new one if it's gone
    state = get_settings().home / state_name
    mid = json.loads(state.read_text())["message_id"] if state.exists() else None
    fmt = {"parse_mode": parse_mode} if parse_mode else {}
    if mid:
        try:
            if markup:
                call("editMessageReplyMarkup", chat_id=chat, message_id=mid, reply_markup=markup)
            else:
                call("editMessageText", chat_id=chat, message_id=mid, text=text, **fmt)
            print(f"updated message {mid} ({state_name})", flush=True)
        except TelegramError as e:
            if "not modified" not in str(e):
                mid = None  # message gone, post a new one
    if not mid:
        mid = call("sendMessage", chat_id=chat, text=text, **fmt, **({"reply_markup": markup} if markup else {}))[
            "message_id"
        ]
        state.write_text(json.dumps({"message_id": mid}))
        print(f"posted message {mid} ({state_name})", flush=True)
    try:
        call("pinChatMessage", chat_id=chat, message_id=mid, disable_notification=True)
    except TelegramError:
        print(f"bot can't pin message {mid}: make it a group admin with 'Pin messages'", flush=True)
    return mid
