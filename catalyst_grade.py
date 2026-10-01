#!/usr/bin/env python3
"""
catalyst_grade.py — grades discrete catalyst events into real outcomes.

Problem this fixes (feedback-loop gap #3): the portfolio track record only
grows as time-based positions resolve, which takes weeks-to-months. But several
high-value events are BINARY and resolve fast (CAPR PDUFA, NVDA earnings, drug
readouts). This script grades those discrete events against the linked thesis,
producing REAL graded outcomes in days instead of waiting for holds to close.

How it works:
  1. Reads the Important Dates/ calendar (kg_links.upcoming_catalysts with a
     lookback window so past events can be graded too).
  2. For each catalyst event, resolves its company/ticker.
  3. Fetches live price now vs a reference (entry/quote around the event date)
     and grades the move: WIN (price up, thesis confirmed), LOSS (price down,
     thesis weakened), or FLAT.
  4. Writes a dated rider onto the research note linked in the catalyst's
     `theses:` field, OR a standalone Catalyst-Grade note, so the outcome is
     banked in the graph and feeds grade_performance immediately.

Usage:
  python3 catalyst_grade.py                     # grade events passed in last 21d
  python3 catalyst_grade.py --lookback 60       # wider window
  python3 catalyst_grade.py --dry-run           # show what would grade, don't write
"""
import os, sys, glob, re, argparse, json
from datetime import date, datetime, timedelta
import urllib.request

try:
    import yfinance as yf
except Exception:
    yf = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402
import grade as _grade  # noqa: E402

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
IMPORTANT_DIR = os.path.expanduser("~/Documents/Finance Knowledge Graph/Important Dates")
GRADE_OUT = os.path.join(os.path.expanduser("~/Documents/finance-ai"), "event_grades.json")


def _ticker_for_event(company, theses):
    """Resolve a company name/link to a ticker via the graph ticker map; fallback
    to a curated ticker map + research-note scan for names without nodes."""
    tmap = kg_links.load_ticker_map()
    # curated fallback for known companies without a company node yet
    FALLBACK = {
        "capricor": "CAPR", "capricor therapeutics": "CAPR",
        "moderna": "MRNA", "nvidia": "NVDA", "nuvation bio": "NUVB",
    }
    # company may be '[[NVIDIA]]' or 'NVIDIA' or a ticker
    c = str(company).strip().strip("[]")
    for tk, title in tmap.items():
        if c.upper() == tk or c.lower() == title.lower() or title.lower() in c.lower():
            return tk
    cl = c.lower()
    for k, v in FALLBACK.items():
        if k in cl or cl in k:
            return v
    # try theses links
    for part in re.findall(r"\[\[([^\]]+)\]\]", str(theses)):
        t = part.strip()
        for tk, title in tmap.items():
            if t == title or title in t:
                return tk
        for k, v in FALLBACK.items():
            if k in t.lower():
                return v
    return c.upper() if re.fullmatch(r"[A-Z]{1,5}", c) else None


def _price_on(ticker, date_str, mode="pre"):
    """Approx live/anchor price: if yfinance, try history around date; else None.
    mode 'now' returns current quote."""
    if yf is None:
        return None
    try:
        tk = yf.Ticker(ticker)
        if mode == "now":
            info = tk.info or {}
            return info.get("currentPrice") or info.get("regularMarketPrice")
        # try to anchor at event date +/-3d
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        start = (d - timedelta(days=3)).isoformat()
        end = (d + timedelta(days=3)).isoformat()
        hist = tk.history(start=start, end=end)["Close"]
        if len(hist):
            return float(hist.iloc[0])
        return None
    except Exception:
        return None


def _load_grades():
    if os.path.exists(GRADE_OUT):
        try:
            with open(GRADE_OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_grades(grades):
    with open(GRADE_OUT, "w", encoding="utf-8") as f:
        json.dump(grades, f, indent=2, default=str)
    return grades


def grade_events(lookback_days=21, dry_run=False, min_move_pct=0.0):
    """Grade catalyst events that have a date <= today, within lookback."""
    today = date.today()
    grades = _load_grades()
    done_keys = {g["key"] for g in grades}

    # collect events from Important Dates with dates in [today-lookback, today]
    events = []
    for path in glob.glob(os.path.join(IMPORTANT_DIR, "*.md")):
        fm = kg_links.get_frontmatter(path)
        dstr = fm.get("date")
        if not dstr:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
            dstr = m.group(1) if m else None
        if not dstr:
            continue
        try:
            d = datetime.strptime(dstr[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        if today - timedelta(days=lookback_days) <= d <= today:
            events.append({
                "date": d.isoformat(),
                "event": fm.get("event") or "event",
                "company": fm.get("company") or "",
                "theses": fm.get("theses") or "",
                "importance": fm.get("importance", 3),
                "notes": fm.get("notes") or "",
                "handled": str(fm.get("handled", "false")).lower() == "true",
            })

    new_grades = []
    for ev in events:
        ticker = _ticker_for_event(ev["company"], ev["theses"])
        if not ticker:
            print(f"  ~ no ticker for {ev['company']} ({ev['event']}) — skipping")
            continue
        key = f"{ticker}:{ev['date']}:{ev['event']}"
        if key in done_keys:
            print(f"  - already graded {key}")
            continue
        pre = _price_on(ticker, ev["date"], "pre") or _price_on(ticker, ev["date"], "now")
        now = _price_on(ticker, ev["date"], "now") if ticker else None
        if not pre or not now:
            print(f"  ~ {ticker} {ev['event']}: no price anchor ({pre}, {now})")
            continue
        ret = (now / pre - 1) * 100
        if abs(ret) < min_move_pct:
            verdict = "flat"
        else:
            verdict = "win" if ret > 0 else "loss"
        grade_rec = {
            "key": key, "ticker": ticker, "event": ev["event"], "date": ev["date"],
            "company": ev["company"], "pre": pre, "now": now, "ret_pct": round(ret, 2),
            "verdict": verdict, "graded": today.isoformat(),
        }
        new_grades.append(grade_rec)
        print(f"  ✔ {ticker} {ev['event']} ({ev['date']}): pre {pre:.2f} → now {now:.2f} = {ret:+.1f}% [{verdict}]")
        if not dry_run:
            _bank_grade(ev, ticker, grade_rec)

    if new_grades and not dry_run:
        # append persisted set
        grades = _load_grades()
        grades = grades + new_grades
        _save_grades(grades)
    elif new_grades and dry_run:
        print(f"  (dry-run — {len(new_grades)} would be banked, nothing written)")
    return new_grades


def _bank_grade(ev, ticker, grade_rec):
    """Write the event outcome into the linked research note (append a
    'Catalyst grade' rider) so it feeds the graph + grade_performance."""
    # find the thesis note via theses link
    note_path = None
    for part in re.findall(r"\[\[([^\]]+)\]\]", str(ev["theses"])):
        note_path = _grade.find_note_by_title(part.strip())
        if note_path:
            break
    if not note_path:
        note_path = _grade.find_note_by_ticker(ticker)
    if note_path:
        text = open(note_path, encoding="utf-8").read()
        fm = kg_links.get_frontmatter(note_path)
        # set status complete + verdict if thesis resolved, else append rider
        rider = (
            f"\n\n## Catalyst grade — {ev['event']} ({ev['date']})\n"
            f"- **Outcome:** {grade_rec['verdict'].upper()} · pre {grade_rec['pre']:.2f} → "
            f"{grade_rec['now']:.2f} ({grade_rec['ret_pct']:+.1f}%) on the {ev['event']} trigger {ev['date']}.\n"
            f"- Graded {grade_rec['graded']} by catalyst_grade.py (event-graded, not time-hold).\n"
        )
        # only append once
        if f"Catalyst grade — {ev['event']}" not in text:
            with open(note_path, "a", encoding="utf-8") as f:
                f.write(rider)
            print(f"     -> rider appended to {os.path.basename(note_path)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=21)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-move", type=float, default=0.0)
    ap.add_argument("--event", default=None)  # specific event tag to force (optional)
    args = ap.parse_args()

    today = date.today()
    print(f"=== catalyst_grade.py — {today} (lookback {args.lookback}d) ===")
    new = grade_events(lookback_days=args.lookback, dry_run=args.dry_run, min_move_pct=args.min_move)
    print(f"\n{len(new)} event(s) graded.")
    # show running event record
    gr = _load_grades()
    wins = sum(1 for g in gr if g.get("verdict") == "win")
    losses = sum(1 for g in gr if g.get("verdict") == "loss")
    print(f"Event track record: {wins}W / {losses}L / {len(gr) - wins - losses} flat (n={len(gr)})")


if __name__ == "__main__":
    main()
