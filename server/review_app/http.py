import gzip
import hashlib
import hmac
import json
import re
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
AUDIO_TTL = 6 * 3600  # an audio link from the detail response works this long


def _audio_sig(cid: str, exp: int) -> str:
    key = hashlib.sha256(b"audio:" + get_settings().token.encode()).digest()
    return hmac.new(key, f"{cid}:{exp}".encode(), hashlib.sha256).hexdigest()


def audio_link(cid: str) -> str:
    # the audio element can't send X-Init-Data, so the signed detail response hands out a signed link
    exp = int(time.time()) + AUDIO_TTL
    return f"/api/audio/{cid}?exp={exp}&sig={_audio_sig(cid, exp)}"


def rate_ok(uid: int, limit: int = 60, window: int = 60) -> bool:
    now = time.time()
    recent = [t for t in _writes.get(uid, []) if now - t < window]
    _writes[uid] = recent + [now]
    return len(recent) < limit


class Handler(BaseHTTPRequestHandler):
    def _head(self, code: int, ctype: str, length: int, extra: dict) -> None:
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", get_settings().origin)
        self.send_header("Access-Control-Allow-Headers", "X-Init-Data, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", extra.pop("Cache-Control", "no-store"))
        self.send_header("Content-Type", ctype)
        for k, val in extra.items():
            self.send_header(k, val)
        self.send_header("Content-Length", str(length))
        self.end_headers()

    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json") -> None:
        gz = ctype == "application/json" and len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "")
        if gz:
            body = gzip.compress(body, 5)
        self._head(code, ctype, len(body), {"Content-Encoding": "gzip"} if gz else {})
        self.wfile.write(body)

    def _audio(self, cid: str, query: str) -> None:
        # streamed with byte ranges so playback starts before the whole file arrives
        q = urllib.parse.parse_qs(query)
        exp, sig = q.get("exp", [""])[0], q.get("sig", [""])[0]
        if not (exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, _audio_sig(cid, int(exp)))):
            return self._json(403, {"error": "audio link expired, reopen the conversation"})
        f = conversations.recording(cid)
        if not f:
            return self._json(404, {"error": "no audio"})
        size = f.stat().st_size
        start, end, code, extra = 0, size - 1, 200, {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if m and (m[1] or m[2]):
            start, end = (int(m[1]), int(m[2] or size - 1)) if m[1] else (max(0, size - int(m[2])), size - 1)
            end = min(end, size - 1)
            if start > end:
                return self._head(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
            code, extra["Content-Range"] = 206, f"bytes {start}-{end}/{size}"
        self._head(code, "audio/mp4" if f.suffix in (".m4a", ".mp4") else "audio/mpeg", end - start + 1, extra)
        try:
            with f.open("rb") as h:
                h.seek(start)
                left = end - start + 1
                while left > 0 and (chunk := h.read(min(65536, left))):
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the player dropped this range for another one

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
        url = urllib.parse.urlparse(self.path)
        if url.path.startswith("/api/audio/"):
            return self._audio(url.path.rsplit("/", 1)[-1], url.query)
        v = self._viewer()
        if not v:
            return
        path = url.path
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
            self._json(200, {**out, "audio": audio_link(out["id"])})
        elif path == "/api/benchmark":
            if not v.full:
                return self._json(403, {"error": "open the review from the cost group"})
            rows = all_rows()
            self._json(200, benchmark(conversations.scan(rows), rows, datetime.now(IST).strftime("%Y-%m-%d")))
        elif path == "/api/team":
            if not v.owner:
                return self._json(403, {"error": "owner only"})
            self._json(200, {"people": team()})
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
