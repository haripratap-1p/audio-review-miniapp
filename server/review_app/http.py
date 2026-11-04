import gzip
import json
import sys
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any

from . import conversations
from .config import IST, LABELS, MAX_BODY, get_settings
from .reports import benchmark
from .roles import roles, set_tech, team_list
from .store import all_rows
from .viewer import Denied, Viewer, team, viewer_from

_writes: dict = {}  # user_id -> recent write timestamps


def rate_ok(uid: int, limit: int = 60, window: int = 60) -> bool:
    now = time.time()
    recent = [t for t in _writes.get(uid, []) if now - t < window]
    _writes[uid] = recent + [now]
    return len(recent) < limit


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json") -> None:
        gz = ctype == "application/json" and len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "")
        if gz:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", get_settings().origin)
        self.send_header("Access-Control-Allow-Headers", "X-Init-Data, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", ctype)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode())

    def _viewer(self) -> Viewer | None:
        try:
            return viewer_from(self.headers.get("X-Init-Data", ""))
        except Denied as e:
            self._json(e.status, {"error": str(e)})
            return None

    def log_message(self, fmt: str, *args: Any) -> None:
        # no query strings or initData in the log
        status = args[1] if len(args) > 1 else ""
        sys.stderr.write(f"[{datetime.now(IST):%F %T}] {self.command} {self.path.split('?')[0]} {status}\n")

    def do_OPTIONS(self) -> None:
        self._send(204)

    def do_GET(self) -> None:
        v = self._viewer()
        if not v:
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/conversations":
            self._json(
                200,
                {
                    "me": v.first_name,
                    "role": v.role,
                    "is_owner": v.owner,
                    "labels": {s: LABELS[s] for s in v.systems},
                    **conversations.listing(v),
                },
            )
        elif path.startswith("/api/conversation/"):
            out = conversations.get(path.rsplit("/", 1)[-1], v)
            if not out:
                return self._json(404, {"error": "not found"})
            self._json(200, out)
        elif path == "/api/benchmark":
            if not v.full:
                return self._json(403, {"error": "open the review from the cost group"})
            rows = all_rows()
            self._json(200, benchmark(conversations.scan(rows), rows, datetime.now(IST).strftime("%Y-%m-%d")))
        elif path == "/api/team":
            if not v.owner:
                return self._json(403, {"error": "owner only"})
            self._json(200, {"people": team()})
        elif path.startswith("/api/audio/"):
            audio = conversations.recording(path.rsplit("/", 1)[-1])
            if not audio:
                return self._json(404, {"error": "no audio"})
            self._send(200, audio.read_bytes(), "audio/mp4" if audio.suffix in (".m4a", ".mp4") else "audio/mpeg")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        v = self._viewer()
        if not v:
            return
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/review", "/api/team"):
            return self._json(404, {"error": "not found"})
        size = int(self.headers.get("Content-Length", "0") or 0)
        if size > MAX_BODY:
            return self._json(413, {"error": "too large"})
        if not rate_ok(v.uid):
            return self._json(429, {"error": "too many votes, wait a minute"})
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            return self._json(400, {"error": "bad request"})
        if path == "/api/team":
            uid, on = body.get("id"), body.get("tech")
            if not v.owner:
                return self._json(403, {"error": "owner only"})
            if (
                not isinstance(uid, int)
                or not isinstance(on, bool)
                or uid == roles().get("owner")
                or uid not in {p["id"] for p in team_list()}
            ):
                return self._json(400, {"error": "bad request"})
            set_tech(uid, on)
            return self._json(200, {"people": team()})
        try:
            out = conversations.vote(
                v,
                str(body.get("id", "")),
                body.get("system"),
                body.get("verdict"),
                body.get("note", ""),
                body.get("lines"),
            )
        except conversations.Rejected as e:
            return self._json(e.status, {"error": str(e)})
        self._json(200, out)
