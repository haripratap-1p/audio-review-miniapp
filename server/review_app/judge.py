import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from typing import Protocol

from .config import IST, REFERENCE, SCORED, get_settings
from .conversations import Conversation, scan
from .store import all_rows, db, judged

MEANINGS = ("same", "partly", "wrong")
RULES = """You check a speech-to-text system against a reference transcript of the same recorded conversation.
Judge meaning only. Ignore spelling, script (Devanagari vs Latin), transliteration, word order, filler words and \
punctuation. Do not count word errors.
For each numbered SYSTEM line, decide whether it says the same thing as the REFERENCE conversation. Lines may be \
split or merged differently, so look for the matching part anywhere in the reference.
- "same": it says the same thing as the reference.
- "partly": part of it matches, but something that matters is missing, added or changed.
- "wrong": it says something different, or it was not said in the reference.
Return exactly one entry for every SYSTEM line, using its number."""
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"line": {"type": "INTEGER"}, "meaning": {"type": "STRING", "enum": list(MEANINGS)}},
                "required": ["line", "meaning"],
            },
        }
    },
    "required": ["lines"],
}


class Gemini(Protocol):
    def post(self, model: str, key: str, body: dict) -> tuple[int, dict]: ...


class HttpGemini:
    base = "https://generativelanguage.googleapis.com/v1beta/models"

    def post(self, model: str, key: str, body: dict) -> tuple[int, dict]:
        # the key goes in a header, never in the URL
        req = urllib.request.Request(
            f"{self.base}/{model}:generateContent",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}


client: Gemini = HttpGemini()


def thinking(model: str) -> dict:
    # Gemini 2.x turns thinking off with a zero budget; later models take a level
    return {"thinkingBudget": 0} if model.startswith("gemini-2") else {"thinkingLevel": "minimal"}


def _flat(text: str) -> str:
    return " ".join(str(text or "").split())


def request_body(ref: list, lines: list, model: str) -> dict:
    text = "REFERENCE:\n" + "\n".join(f"- {_flat(t.get('text'))}" for t in ref)
    text += "\n\nSYSTEM LINES:\n" + "\n".join(f"{n}. {_flat(t.get('text'))}" for n, t in enumerate(lines, 1))
    return {
        "systemInstruction": {"parts": [{"text": RULES}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "thinkingConfig": thinking(model),
        },
    }


def parse(resp: dict, n: int) -> dict | None:
    # model reply -> {0-based line: meaning}; bad or out-of-range entries dropped; None if not JSON at all
    try:
        text = "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])
        items = json.loads(text)["lines"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not isinstance(items, list):
        return None
    out: dict = {}
    for x in items:
        if not isinstance(x, dict):
            continue
        ln, m = x.get("line"), x.get("meaning")
        if isinstance(ln, int) and not isinstance(ln, bool) and 1 <= ln <= n and m in MEANINGS:
            out.setdefault(ln - 1, m)
    return out


def score(meanings: dict, n: int) -> float:
    # share of "same" lines over every system line; partly counts half, missing lines count as not same
    return round(sum({"same": 1.0, "partly": 0.5}.get(m, 0.0) for m in meanings.values()) / n, 4) if n else 0.0


def usage(resp: dict) -> tuple[int, int]:
    u = resp.get("usageMetadata") or {}
    return int(u.get("promptTokenCount") or 0), int(u.get("candidatesTokenCount") or 0) + int(
        u.get("thoughtsTokenCount") or 0
    )


def cost(tokens_in: int, tokens_out: int) -> float:
    st = get_settings()
    return (tokens_in * st.judge_price_in + tokens_out * st.judge_price_out) / 1e6


def _quota(code: int, resp: dict) -> bool:
    return code == 429 or (resp.get("error") or {}).get("status") == "RESOURCE_EXHAUSTED"


def usable(r: dict | None) -> bool:
    return bool(r and not r.get("error") and not r.get("skipped") and r.get("turns"))


def pairs(convs: list[Conversation]) -> list[tuple[Conversation, str]]:
    # unjudged (conversation, system) pairs: unreviewed conversations first, then human-reviewed; newest first in each
    done = judged()
    reviewed = [any(c.reviews.get(s) for s in SCORED) for c in convs]
    ordered = [c for c, r in zip(convs, reviewed, strict=True) if not r] + [
        c for c, r in zip(convs, reviewed, strict=True) if r
    ]
    return [
        (c, s)
        for c in ordered
        if usable(c.results[REFERENCE])
        for s in SCORED
        if usable(c.results[s]) and (c.id, s) not in done
    ]


def _save(c: Conversation, s: str, meanings: dict, n: int, model: str, tin: int, tout: int, usd: float) -> None:
    now = datetime.now(IST).isoformat(timespec="seconds")
    ref_model = c.results[REFERENCE].get("model", "")
    with db() as conn:
        conn.execute("DELETE FROM judge_lines WHERE conv=? AND system=?", (c.id, s))
        conn.executemany("INSERT INTO judge_lines VALUES (?,?,?,?)", [(c.id, s, k, m) for k, m in meanings.items()])
        conn.execute(
            "INSERT OR REPLACE INTO judge_runs VALUES (?,?,?,?,?,?,?,?,?)",
            (c.id, s, score(meanings, n), ref_model, model, tin, tout, usd, now),
        )


def run(dry: bool = False, limit: int | None = None) -> dict:
    st = get_settings()
    cap = st.judge_cap if limit is None else min(limit, st.judge_cap)
    todo = pairs(scan(all_rows()))
    stats = {"judged": 0, "skipped": 0, "cost": 0.0}
    keys, k, sent = st.gemini_keys, 0, 0
    if not dry and not keys:
        print("judge: GEMINI_API_KEYS is not set", flush=True)
    for c, s in todo:
        lines = c.results[s]["turns"]
        if dry:
            if sent < cap:
                sent += 1
                print(f"would judge {c.key} {s} ({len(lines)} lines)", flush=True)
                stats["judged"] += 1
            else:
                stats["skipped"] += 1
            continue
        if sent >= cap or k >= len(keys):
            stats["skipped"] += 1
            continue
        body = request_body(c.results[REFERENCE]["turns"], lines, st.judge_model)
        sent += 1
        while True:
            try:
                code, resp = client.post(st.judge_model, keys[k], body)
            except OSError as e:
                code, resp = 0, {"error": {"message": type(e).__name__}}
            if not _quota(code, resp) or k + 1 >= len(keys):
                break
            print(f"judge: key {k + 1} of {len(keys)} out of quota, switching", flush=True)
            k += 1  # same request on the next key
        if _quota(code, resp):
            k = len(keys)  # every key is out of quota: stop sending this run
        tin, tout = usage(resp)
        usd = cost(tin, tout)
        stats["cost"] += usd
        meanings = parse(resp, len(lines)) if code == 200 else None
        if meanings is None:
            msg = _flat((resp.get("error") or {}).get("message") or "unreadable reply")[:160]
            for key in keys:
                msg = msg.replace(key, "***")
            print(f"judge failed {c.key} {s}: HTTP {code} {msg}", flush=True)
            stats["skipped"] += 1
            continue
        _save(c, s, meanings, len(lines), st.judge_model, tin, tout, usd)
        stats["judged"] += 1
    verb = "would judge" if dry else "judged"
    print(f"{verb} {stats['judged']}, skipped {stats['skipped']}, cost ${stats['cost']:.4f}", flush=True)
    return stats


def main(argv: list[str]) -> None:
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    run(dry="--dry-run" in argv, limit=limit)


if __name__ == "__main__":
    main(sys.argv[1:])
