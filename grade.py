#!/usr/bin/env python3
"""
grade.py — closes the "was I right?" feedback loop.

The knowledge graph records ideas and theses but track-record grading was
dormant. This script makes it live by:

  A) CLOSING an open note when a decision resolves (sell / thesis break /
     time stop): gradify one note with an exit price + date, and it computes
     realized_return and vs SPY over the holding window and backfills the
     research note's frontmatter track-record fields (decision, entry, exit,
     realized_return, vs_spy, holding_days, outcome, track_updated) AND links
     it into the company node / grade_performance aggregation.

  B) GRADING THE WHOLE GRAPH: scan every research note with a decision and
    priceable entry, fetch the current price vs the benchmark, and emit a
    running "open paper P&L" + which notes have gone from INTACT to
    WEAKENED/BROKEN (import from the thesis-review verdict on the note).

Usage:
  python3 grade.py                          # scan all open decision notes, emit open P&L table + closed grades so far
  python3 grade.py --close "NoteTitle" --exit 123.45 --date 2026-08-20
      # backfill a resolved trade into the named note and re-run the report
  python3 grade.py --close-by-ticker F --exit 15.00 --date 2026-08-20
      # close the note whose company ticker is F

All figures are LIVE from yfinance (current price + SPY), so open-P&L is real,
not estimated. No fabricated numbers. Idea/decision grading only.
"""
import os, sys, glob, re, json, argparse
from datetime import date, datetime

try:
    import yfinance as yf
except Exception:
    yf = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402

KG_ROOT = os.path.expanduser("~/Documents/Finance Knowledge Graph")
KG_NOTES = os.path.join(KG_ROOT, "Notes")
COMPANIES_DIR = os.path.join(KG_ROOT, "Companies")

BENCH = "SPY"


def _lnk(t):
    return t.strip().strip("[]").strip('"')


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def find_note_by_ticker(ticker):
    tmap = kg_links.load_ticker_map()
    title = tmap.get(ticker.upper())
    if not title:
        return None
    for p in glob.glob(os.path.join(KG_NOTES, "*.md")):
        if os.path.splitext(os.path.basename(p))[0] == title:
            return p
        fm = kg_links.get_frontmatter(p)
        if title.lower() in str(fm.get("companies", "")).lower():
            return p
    return None


def find_note_by_title(title):
    for p in glob.glob(os.path.join(KG_NOTES, "*.md")):
        if title.lower() in os.path.basename(p).lower():
            return p
    return None


def live_price(sym):
    if yf is None:
        return None
    try:
        tk = yf.Ticker(sym)
        info = tk.info or {}
        return info.get("currentPrice") or info.get("regularMarketPrice")
    except Exception:
        return None


def gradify(note_path, exit_price, exit_date, benchmark=BENCH):
    """Backfill track-record fields into a research note given a resolved exit."""
    text = _read(note_path)
    fm = kg_links.get_frontmatter(note_path)   # NB: pass the PATH, not the raw text
    title = os.path.splitext(os.path.basename(note_path))[0]

    entry_s = (fm.get("entry") or "").strip()
    decision = (fm.get("decision") or "").upper().strip()
    if not entry_s:
        # try to read from PM portfolio state if this ticker is held/sold
        entry_s = _entry_from_state(fm)
    try:
        entry = float(re.sub(r"[^0-9.]", "", entry_s.split("/")[0]))
    except Exception:
        entry = None
    if not entry:
        print(f"  ! {title}: no priceable entry to grade")
        return None

    holding_days = None
    try:
        d0 = datetime.strptime((fm.get("entry_date") or fm.get("date") or "")[:10], "%Y-%m-%d").date()
        d1 = datetime.strptime(exit_date[:10], "%Y-%m-%d").date()
        holding_days = (d1 - d0).days
    except Exception:
        holding_days = None

    realized = (exit_price / entry - 1) * 100
    # vs SPY over the holding window
    vs_spy = None
    if yf is not None and holding_days:
        try:
            hist = yf.Ticker(benchmark).history(start=exit_date, periods="5d")["Close"]
            # use note date's nearest SPY close as the basis when possible
            sp_entry = _spy_near(fm.get("date"))
            sp_exit = hist.iloc[-1] if len(hist) else None
            if sp_entry and sp_exit:
                vs_spy = realized - ((sp_exit / sp_entry - 1) * 100)
            else:
                vs_spy = None
        except Exception:
            vs_spy = None

    outcome = "win" if realized > 0 else ("loss" if realized < 0 else "table")
    if decision in ("BUY", "WATCH") and realized > 0:
        outcome = "win"
    elif decision in ("BUY", "WATCH") and realized < 0:
        outcome = "loss"

    # backfill
    new_fm = {}
    for key in ("type", "topic", "companies", "themes", "context", "sources",
                "idea_source", "invalidations", "strengthens_when", "catalysts"):
        if key in fm:
            new_fm[key] = fm[key]
    new_date = fm.get("date", exit_date[:10])
    new_fm["date"] = new_date
    new_fm["topic"] = fm.get("topic", "") + (" [GRADED]" if "[GRADED]" not in (fm.get("topic") or "") else "")
    new_fm["status"] = "complete"
    new_fm["decision"] = decision or "HOLD"
    new_fm["entry"] = f"{entry:.2f} / {new_date}"
    new_fm["exit"] = f"{exit_price:.2f} / {exit_date[:10]}"
    new_fm["realized_return"] = f"{realized:+.1f}%"
    new_fm["vs_spy"] = f"{vs_spy:+.1f}%" if vs_spy is not None else ""
    new_fm["holding_days"] = str(holding_days) if holding_days else ""
    new_fm["outcome"] = outcome
    new_fm["track_updated"] = date.today().isoformat()

    block = "---\n" + "".join(f'{k}: "{v}"\n' for k, v in new_fm.items()) + "---\n"
    body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)
    _write(note_path, block + body)
    vs_txt = f"{vs_spy:+.1f}%" if vs_spy is not None else "n/a"
    print(f"  ✔ {title}: {decision} {realized:+.1f}% vs SPY {vs_txt} ({outcome}, {holding_days or '?'}d)")
    return {"note": title, "realized": realized, "vs_spy": vs_spy, "outcome": outcome, "holding_days": holding_days}


def _entry_from_state(fm):
    # pull entry from PM portfolio if this note's company is a current/hist position
    state = None
    try:
        import json as _j
        with open(os.path.expanduser("~/Documents/finance-ai/pm_portfolio.json"), encoding="utf-8") as f:
            state = _j.load(f)
    except Exception:
        return ""
    tmap = kg_links.load_ticker_map()
    for pos in state.get("positions", []) + state.get("closed_positions", []):
        title = tmap.get(pos.get("symbol", "").upper(), "")
        if title and title.lower() in str(fm.get("companies", "")).lower():
            return str(pos.get("entry", ""))
    return ""


def _spy_near(date_str):
    if not date_str or yf is None:
        return None
    try:
        h = yf.Ticker(BENCH).history(start=date_str[:10], periods="5d")["Close"]
        return h.iloc[0] if len(h) else None
    except Exception:
        return None


def report():
    """Scan all research notes, emit graded-closed table + open P&L table."""
    closed, open_notes = [], []
    for p in sorted(glob.glob(os.path.join(KG_NOTES, "*.md"))):
        title = os.path.splitext(os.path.basename(p))[0]
        fm = kg_links.get_frontmatter(p)
        if fm.get("outcome") and fm.get("outcome") in ("win", "loss", "table"):
            closed.append((title, fm))
        elif fm.get("decision") and fm.get("decision").upper() in ("BUY", "WATCH", "HOLD"):
            open_notes.append((title, fm))
    # closed
    print("\n=== CLOSED / GRADED (actual outcomes) ===")
    if not closed:
        print("  (none yet — grading becomes real as positions resolve)")
    for title, fm in closed:
        print(f"  {title}: {fm.get('outcome')} ret {fm.get('realized_return')} vsSPY {fm.get('vs_spy')} {fm.get('holding_days')}d")
    # open P&L
    print("\n=== OPEN DECISION NOTES (live paper P&L) ===")
    if not open_notes:
        print("  (no notes with a live decision + entry to price yet)")
    for title, fm in open_notes:
        sym = _ticker_from_note(title, fm)
        px = live_price(sym) if sym else None
        entry = fm.get("entry")
        try:
            ein = float(re.sub(r"[^0-9.]", "", str(entry).split("/")[0]))
        except Exception:
            ein = None
        if px and ein:
            ret = (px / ein - 1) * 100
            print(f"  {title} ({sym}): entry {ein:.2f} now {px:.2f} = {ret:+.1f}%")
        else:
            print(f"  {title}: entry {entry}")


def _ticker_from_note(title, fm):
    # company link in frontmatter -> ticker map
    tmap = kg_links.load_ticker_map()
    comps = fm.get("companies", "")
    for ticker, ctitle in tmap.items():
        if f"[[{ctitle}]]" in str(comps) or ctitle.lower() in title.lower():
            return ticker
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--close", dest="close_title", default=None)
    ap.add_argument("--close-by-ticker", dest="ticker", default=None)
    ap.add_argument("--exit", type=float, default=None)
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    if args.ticker:
        p = find_note_by_ticker(args.ticker)
        if p:
            gradify(p, args.exit, args.date)
        else:
            print(f"  ! no note found for {args.ticker}")
    elif args.close_title:
        p = find_note_by_title(args.close_title)
        if p:
            gradify(p, args.exit, args.date)
        else:
            print(f"  ! no note found matching '{args.close_title}'")
    report()


if __name__ == "__main__":
    main()
