import html
from datetime import datetime

from .config import IST, LABELS, REFERENCE, SCORED, get_settings
from .conversations import Conversation, scan
from .launcher import tunnel_sub
from .store import all_rows, judged
from .telegram import call, launch_url

AI_OK = 0.8  # a judge score at or above this reads as "ok" when compared with the team's verdict


def eod_text(
    convs: list[Conversation],
    rows: list,
    today: str,
    systems: tuple = ("pipeline",),
    title: str = "Review EOD",
    judge: dict | None = None,
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
        if judge is not None:
            ai = ai_score(convs, s, judge)
            lines.append(f"• {LABELS[s]} AI judge: {pct_text(ai['pct'])} ({ai['judged']} judged)")
    if judge is not None:
        ag = agreement(convs, judge)["all"]
        lines.append(f"• AI judge agrees with people: {pct_text(ag['pct'])} ({ag['pairs']})")
        lines.append(f"• {LABELS[REFERENCE]}: not scored, model {', '.join(ref_models(convs)) or 'not known'}")
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


def pct_text(p: int | None) -> str:
    return f"{p}%" if p is not None else "-"


def ai_score(sel: list[Conversation], s: str, judge: dict) -> dict:
    # mean judge score over judged conversations; kept apart from the people's numbers
    sc = [judge[(c.id, s)]["score"] for c in sel if (c.id, s) in judge]
    return {"judged": len(sc), "pct": round(100 * sum(sc) / len(sc)) if sc else None}


def agreement(sel: list[Conversation], judge: dict) -> dict:
    # share of people-checked (system, conversation) pairs where the judge's ok/bad matches the team's verdict
    def share(ps: list) -> dict:
        same = sum(("ok" if judge[(c.id, s)]["score"] >= AI_OK else "bad") == c.scored(s) for c, s in ps)
        return {"pairs": len(ps), "pct": round(100 * same / len(ps)) if ps else None}

    by = {s: [(c, s) for c in sel if (c.id, s) in judge and c.scored(s)] for s in SCORED}
    return {"all": share([p for ps in by.values() for p in ps]), **{s: share(ps) for s, ps in by.items()}}


def ref_models(sel: list[Conversation]) -> list:
    return sorted({c.results[REFERENCE].get("model") or "" for c in sel if c.available(REFERENCE)} - {""})


def benchmark(convs: list[Conversation], rows: list, today: str) -> dict:
    calls = [c for c in convs if c.kind == "call"]
    store = [c for c in convs if c.kind == "in-store"]
    people: dict = {}
    for r in rows:
        p = people.setdefault(r["user_id"], {"name": r["user_name"], "today": 0, "total": 0})
        p["total"] += 1
        p["today"] += r["ts"][:10] == today
    days = sorted({c.date for c in convs})[-14:]
    judge = judged()
    return {
        "labels": {s: LABELS[s] for s in SCORED},
        "systems": {
            s: {
                "all": score(convs, s),
                "call": score(calls, s),
                "in-store": score(store, s),
                "ai": ai_score(convs, s, judge),
            }
            for s in SCORED
        },
        "agreement": agreement(convs, judge),
        "reference": {"label": LABELS[REFERENCE], "models": ref_models(convs)},
        "days": [{"date": d, **{s: score([c for c in convs if c.date == d], s)["pct"] for s in SCORED}} for d in days],
        "reviewers": sorted(people.values(), key=lambda p: -p["total"]),
    }


def post_eod(dry: bool) -> None:
    st = get_settings()
    today = datetime.now(IST).strftime("%Y-%m-%d")
    rows = all_rows()
    convs = scan(rows)
    text = eod_text(convs, rows, today)
    bench = eod_text(convs, rows, today, SCORED, "Benchmark", judged())
    if dry:
        print(text, bench, sep="\n\n")
        return
    if st.cost_chat:
        call("sendMessage", chat_id=st.cost_chat, text=bench, parse_mode="HTML")
    sub = tunnel_sub()
    markup = {"inline_keyboard": [[{"text": "📝 Open review", "url": launch_url(sub)}]]} if sub else None
    call("sendMessage", chat_id=st.chat, text=text, parse_mode="HTML", **({"reply_markup": markup} if markup else {}))
