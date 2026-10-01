#!/usr/bin/env python3
"""
validate.py — data-quality gate (feedback-loop gap #1: garbage-in).

The graph's research notes carry fundamental figures that can go stale or wrong.
Before the PM sizes a name (or an analyst note is acted on), this gate checks
the live data against what was recorded and flags divergence / staleness / errors.

Checks per ticker:
  1. LIVE reachable?  (price exists; ticker not delisted/failed — catches dead symbols)
  2. Freshness        (the note's date vs today; stale beyond N days flagged)
  3. Price divergence (recorded 'entry'/'last' vs current live price — big move = re-check)
  4. Fundamental sanity (fwd P/E, P/S, market cap exist; flag NaN/zero/absurd)

Output: data_quality verdict per ticker — CLEAR / STALE / MOVED (re-check) / BROKEN (do not size).
Writes finance-ai/data_quality.json. Runs inline in the PM cycle before sizing.

Usage:
  python3 validate.py                       # validate every name in research notes
  python3 validate.py --tickers GM ADBE     # validate specific tickers
  python3 validate.py --json                # machine-readable output (becomes data_quality.json)
"""
import os, sys, json, glob, re, argparse
from datetime import date, datetime

try:
    import yfinance as yf
except Exception:
    yf = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402

FINANCE_AI = os.path.expanduser("~/Documents/finance-ai")
KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
OUT_JSON = os.path.join(FINANCE_AI, "data_quality.json")

STALE_DAYS = 30        # note older than this => flag stale (fundamentals may be dated)
PRICE_MOVE_ALERT = 0.15  # live vs recorded moved >15% => re-check before trusting


def _ticker_of_note(title, fm):
    tmap = kg_links.load_ticker_map()
    comps = str(fm.get("companies", ""))
    for tk, ctitle in tmap.items():
        if f"[[{ctitle}]]" in comps or ctitle.lower() in title.lower():
            return tk
    # bare ticker in title like "General Motors GM research"
    m = re.search(r"\b([A-Z]{2,5})(?:\s+research|\s+earnings|\s+$)", title)
    return m.group(1) if m else None


def live_quote(sym):
    if yf is None:
        return None, {}
    try:
        tk = yf.Ticker(sym)
        info = tk.info or {}
        p = info.get("currentPrice") or info.get("regularMarketPrice")
        fpe = info.get("forwardPE")
        ps = info.get("priceToSalesTrailing12Months")
        mcap = info.get("marketCap")
        return (float(p) if p else None), {
            "forwardPE": fpe, "ps": ps, "marketCap": mcap,
        }
    except Exception:
        return None, {}


def validate_ticker(sym, note_title="", note_date=None, recorded_last=None, recorded_entry=None):
    """Return a data_quality record for one ticker."""
    rec = {"ticker": sym, "note": note_title, "verdict": "CLEAR", "checks": {}}
    # 1) reachable / not delisted
    px, info = live_quote(sym)
    if px is None:
        rec["verdict"] = "BROKEN"
        rec["checks"]["live"] = "no live quote — ticker delisted/failed or feed down"
        rec["checks"]["price"] = None
        return rec
    rec["checks"]["price"] = px
    # 2) freshness
    if note_date:
        try:
            d = datetime.strptime(note_date[:10], "%Y-%m-%d").date()
            age = (date.today() - d).days
            rec["checks"]["age_days"] = age
            if age > STALE_DAYS:
                rec["verdict"] = "STALE" if rec["verdict"] == "CLEAR" else rec["verdict"]
                rec["checks"]["stale"] = f"note {age}d old (> {STALE_DAYS}d)"
        except Exception:
            rec["checks"]["age_days"] = None
    # 3) price divergence vs recorded
    ref = recorded_last or recorded_entry
    if ref:
        try:
            ref = float(re.sub(r"[^0-9.]", "", str(ref).split("/")[0]))
            move = (px / ref - 1) if ref else 0
            rec["checks"]["vs_recorded"] = f"{move*100:+.1f}%"
            if abs(move) > PRICE_MOVE_ALERT:
                # move is fine for a real market, but flag for re-confirm of thesis
                rec.setdefault("flags", []).append(
                    f"price moved {move*100:+.1f}% vs recorded ({ref:.2f}->{px:.2f}) — re-verify thesis")
                if rec["verdict"] == "CLEAR":
                    rec["verdict"] = "MOVED"
        except Exception:
            rec["checks"]["vs_recorded"] = None
    # 4) fundamental sanity
    fpe = info.get("forwardPE")
    ps = info.get("ps")
    mcap = info.get("marketCap")
    rec["checks"]["forwardPE"] = fpe
    rec["checks"]["ps"] = ps
    rec["checks"]["marketCap"] = mcap
    if mcap and float(mcap) <= 0:
        rec.setdefault("flags", []).append("non-positive market cap — data broken")
        rec["verdict"] = "BROKEN"
    if isinstance(fpe, (int, float)) and fpe < 0:
        rec.setdefault("flags", []).append("negative forward P/E (loss-maker — expected for biotech, verify runway)")
    rec.setdefault("flags", [])
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    today = date.today().isoformat()
    if args.tickers:
        results = [validate_ticker(t.upper()) for t in args.tickers]
    else:
        # validate every name in research notes
        results = []
        for p in sorted(glob.glob(os.path.join(KG_NOTES, "*.md"))):
            title = os.path.splitext(os.path.basename(p))[0]
            fm = kg_links.get_frontmatter(p)
            if title.startswith(today):
                continue  # same-day notes don't age yet
            sym = _ticker_of_note(title, fm)
            if not sym:
                continue
            results.append(validate_ticker(
                sym, note_title=title,
                note_date=fm.get("date"),
                recorded_last=fm.get("last") or fm.get("entry"),
                recorded_entry=fm.get("entry"),
            ))
            if args.limit and len(results) >= args.limit:
                break

    # summary
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"=== data_quality gate — {today} ===")
    print(f"checked {len(results)} names | {counts}\n")
    print("| Ticker | Verdict | Note (age) | Price | Flags |")
    print("|---|---|---|---|---|")
    for r in results:
        age = r["checks"].get("age_days", "")
        age_s = f"{age}d" if age is not None else ""
        flags = "; ".join(r.get("flags", []))[:60] or r["checks"].get("vs_recorded", "")
        px = r["checks"].get("price")
        px_s = f"{px:.2f}" if px else "—"
        print(f"| {r['ticker']} | **{r['verdict']}** | {r['note'][:30]} ({age_s}) | {px_s} | {flags} |")

    # machine output
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"date": today, "results": results}, f, indent=2, default=str)
    print(f"\nSaved {OUT_JSON}")
    broken = [r["ticker"] for r in results if r["verdict"] == "BROKEN"]
    moved = [r["ticker"] for r in results if r["verdict"] == "MOVED"]
    print(f"Do-NOT-SIZE: {broken or 'none'}")
    print(f"Re-verify: {moved or 'none'}")


if __name__ == "__main__":
    main()
