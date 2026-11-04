import html
from datetime import datetime

from .config import IST, LABELS, SYSTEMS, get_settings
from .conversations import Conversation, scan
from .launcher import tunnel_sub
from .store import all_rows
from .telegram import tg_api


def eod_text(
    convs: list[Conversation], rows: list, today: str, systems: tuple = ("pipeline",), title: str = "Review EOD"
) -> str:
    today_rows = [r for r in rows if r["ts"][:10] == today and r["system"] in systems]
    notes = [r for r in sorted(today_rows, key=lambda r: r["ts"], reverse=True) if r["note"]][:3]
    lines = [
        f"📊 <b>{title} — {datetime.strptime(today, '%Y-%m-%d').strftime('%d %b')}</b>",
        f"• Today: {len(today_rows)} votes by {len({r['user_id'] for r in today_rows})} reviewer(s)",
    ]
    scores = []
    for s in systems:
        sc = score(convs, s)
        pct = f"{sc['pct']}%" if sc["pct"] is not None else "-"
        lines.append(f"• {LABELS[s]}: checked {sc['checked']} of {sc['available']}, {pct} correct")
        if sc["pct"] is not None:
            scores.append((sc["pct"], LABELS[s]))
    if len(systems) > 1:
        top = [n for p, n in scores if p == max(scores)[0]] if scores else []
        best = "—" if not top else " / ".join(top) + (" (tie)" if len(top) > 1 else "")
        lines.append(f"• 🏆 Best so far: <b>{best}</b>")
    if notes:
        lines.append("\n<b>Key notes today:</b>")
        lines += [
            f"• {html.escape(r['user_name'])} on {LABELS.get(r['system'], '?')}: {html.escape(r['note'][:120])}"
            for r in notes
        ]
    left = sum(not all(c.verdict(s) for s in systems if c.available(s)) for c in convs)
    if left:
        lines.append(f"\n👉 {left} conversation(s) still to review")
    return "\n".join(lines)


def score(sel: list[Conversation], s: str) -> dict:
    have = [c for c in sel if c.available(s)]
    checked = [c for c in have if c.scored(s)]
    ok = sum(c.scored(s) == "ok" for c in checked)
    return {
        "available": len(have),
        "checked": len(checked),
        "correct": ok,
        "pct": round(100 * ok / len(checked)) if checked else None,
    }


def benchmark(convs: list[Conversation], rows: list, today: str) -> dict:
    calls = [c for c in convs if c.kind == "call"]
    store = [c for c in convs if c.kind == "in-store"]
    people: dict = {}
    for r in rows:
        p = people.setdefault(r["user_id"], {"name": r["user_name"], "today": 0, "total": 0})
        p["total"] += 1
        p["today"] += r["ts"][:10] == today
    days = sorted({c.date for c in convs})[-14:]
    return {
        "labels": LABELS,
        "systems": {s: {"all": score(convs, s), "call": score(calls, s), "in-store": score(store, s)} for s in SYSTEMS},
        "days": [{"date": d, **{s: score([c for c in convs if c.date == d], s)["pct"] for s in SYSTEMS}} for d in days],
        "reviewers": sorted(people.values(), key=lambda p: -p["total"]),
    }


def post_eod(dry: bool) -> None:
    st = get_settings()
    today = datetime.now(IST).strftime("%Y-%m-%d")
    rows = all_rows()
    convs = scan(rows)
    text = eod_text(convs, rows, today)
    bench = eod_text(convs, rows, today, SYSTEMS, "Benchmark")
    if dry:
        print(text, bench, sep="\n\n")
        return
    if st.cost_chat:
        tg_api("sendMessage", chat_id=st.cost_chat, text=bench, parse_mode="HTML")
    sub = tunnel_sub()
    markup = (
        {"inline_keyboard": [[{"text": "📝 Open review", "url": f"{st.app_link}?startapp={sub}"}]]} if sub else None
    )
    tg_api("sendMessage", chat_id=st.chat, text=text, parse_mode="HTML", **({"reply_markup": markup} if markup else {}))
