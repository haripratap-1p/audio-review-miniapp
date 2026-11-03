import gzip
import json
import subprocess
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any

from .config import IST, LABELS, MAX_BODY, SYSTEMS, get_settings
from .reports import benchmark
from .results import collect
from .roles import roles, set_tech, team_list
from .store import all_rows, db
from .telegram import check_init_data, is_member, mode, view
from .views import clean_lines, detail, light, line_info, overview, rate_ok


def _name(u: dict) -> str:
    return " ".join(filter(None, [u.get("first_name"), u.get("last_name")])) or u.get("username") or str(u["id"])


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

    def _user(self) -> dict | None:
        st = get_settings()
        u = check_init_data(self.headers.get("X-Init-Data", ""), st.token)
        if not u:
            self._json(401, {"error": "session expired"})
            return None
        u["_mode"] = mode(u.get("_sp", ""))
        if not is_member(u["id"], st.cost_chat if u["_mode"] == "cost" else st.chat):
            self._json(403, {"error": "not a group member"})
            return None
        with db() as c:
            c.execute(
                "INSERT INTO visitors VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, "
                "username=excluded.username, last_seen=excluded.last_seen",
                (u["id"], _name(u)[:80], u.get("username", ""), datetime.now(IST).isoformat(timespec="seconds")),
            )
        return u

    def log_message(self, fmt: str, *args: Any) -> None:
        # no query strings or initData in the log
        status = args[1] if len(args) > 1 else ""
        sys.stderr.write(f"[{datetime.now(IST):%F %T}] {self.command} {self.path.split('?')[0]} {status}\n")

    def do_OPTIONS(self) -> None:
        self._send(204)

    def do_GET(self) -> None:
        u = self._user()
        if not u:
            return
        path = urllib.parse.urlparse(self.path).path
        sysv, full = view(u), u["_mode"] == "cost"
        owner = full and u["id"] == roles().get("owner")
        today = datetime.now(IST).strftime("%Y-%m-%d")
        if path == "/api/conversations":
            rows = all_rows()
            items = collect(rows, u["id"])
            self._json(
                200,
                {
                    "me": u.get("first_name", ""),
                    "role": "tech" if full else "general",
                    "is_owner": owner,
                    "labels": {s: LABELS[s] for s in sysv},
                    "items": [light(i, sysv) for i in items],
                    **overview(items, rows, u["id"], today, sysv),
                },
            )
        elif path.startswith("/api/conversation/"):
            cid = path.rsplit("/", 1)[-1]
            item = next((i for i in collect(all_rows(), u["id"]) if i["id"] == cid), None)
            if not item:
                return self._json(404, {"error": "not found"})
            out = detail(item, sysv)
            out["lines"] = line_info(cid, u["id"], sysv, {s: item["votes"][s]["mine"] for s in sysv}, full)
            self._json(200, out)
        elif path == "/api/benchmark":
            if not full:
                return self._json(403, {"error": "open the review from the cost group"})
            rows = all_rows()
            self._json(200, benchmark(collect(rows), rows, today))
        elif path == "/api/team":
            if not owner:
                return self._json(403, {"error": "owner only"})
            self._json(200, {"people": team_list()})
        elif path.startswith("/api/audio/"):
            cid = path.rsplit("/", 1)[-1]
            js = next((i["_js"] for i in collect([]) if i["id"] == cid), None)
            audio = next(js.parent.joinpath("audio").glob(js.stem + ".*"), None) if js else None
            if not audio:
                return self._json(404, {"error": "no audio"})
            if audio.suffix == ".mp4":
                m4a = js.with_suffix(".m4a")  # in-store CCTV clip: serve the sound only
                if not m4a.exists():
                    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-vn", "-c:a", "copy", str(m4a)]
                    subprocess.run(cmd, check=True)
                audio = m4a
            self._send(200, audio.read_bytes(), "audio/mp4" if audio.suffix in (".m4a", ".mp4") else "audio/mpeg")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        u = self._user()
        if not u:
            return
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/review", "/api/team"):
            return self._json(404, {"error": "not found"})
        size = int(self.headers.get("Content-Length", "0") or 0)
        if size > MAX_BODY:
            return self._json(413, {"error": "too large"})
        if not rate_ok(u["id"]):
            return self._json(429, {"error": "too many votes, wait a minute"})
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            return self._json(400, {"error": "bad request"})
        if path == "/api/team":
            r = roles()
            uid, on = body.get("id"), body.get("tech")
            if u["_mode"] != "cost" or u["id"] != r.get("owner"):
                return self._json(403, {"error": "owner only"})
            if (
                not isinstance(uid, int)
                or not isinstance(on, bool)
                or uid == r.get("owner")
                or uid not in {p["id"] for p in team_list()}
            ):
                return self._json(400, {"error": "bad request"})
            set_tech(uid, on)
            return self._json(200, {"people": team_list()})
        cid, system, v = str(body.get("id", "")), body.get("system"), body.get("verdict")
        conv = next((i for i in collect([]) if i["id"] == cid), None)
        if system not in SYSTEMS or v not in ("ok", "bad", "clear") or not conv:
            return self._json(400, {"error": "bad request"})
        if system not in view(u):
            return self._json(403, {"error": "not allowed"})
        lines = clean_lines(body.get("lines"), len((conv.get(system) or {}).get("turns") or []))
        if lines is None:
            return self._json(400, {"error": "bad line marks"})
        name = _name(u)
        now = datetime.now(IST).isoformat()
        with db() as c:
            # one submit replaces my whole review of this system: overall verdict plus every line mark
            c.execute("DELETE FROM line_reviews WHERE conv=? AND system=? AND user_id=?", (cid, system, u["id"]))
            if v == "clear":
                c.execute("DELETE FROM reviews WHERE conv=? AND system=? AND user_id=?", (cid, system, u["id"]))
            else:
                c.execute(
                    "INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?,?)",
                    (cid, system, u["id"], name[:80], v, str(body.get("note", ""))[:500], now),
                )
                c.executemany(
                    "INSERT INTO line_reviews VALUES (?,?,?,?,?,?,?,?)",
                    [(cid, system, ln, u["id"], name[:80], lv, ln_note, now) for ln, (lv, ln_note) in lines.items()],
                )
        item = next(i for i in collect(all_rows(), u["id"]) if i["id"] == cid)
        sysv = view(u)
        self._json(
            200,
            {
                "votes": detail(item, sysv)["votes"],
                "lines": line_info(
                    cid, u["id"], sysv, {s: item["votes"][s]["mine"] for s in sysv}, u["_mode"] == "cost"
                ),
            },
        )
