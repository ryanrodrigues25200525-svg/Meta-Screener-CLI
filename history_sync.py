#!/usr/bin/env python3
"""history_sync.py — incremental refresh of the Finance KG historical layer.

Run ON THE HOST with the venv that has yfinance (cron-safe, idempotent):

    env -u PYTHONPATH ~/venvs/openbb-venv/bin/python ~/Documents/finance-ai/history_sync.py --prices
    env -u PYTHONPATH ~/venvs/openbb-venv/bin/python ~/Documents/finance-ai/history_sync.py --fundamentals

Why this exists: Datasets/History/ holds a backfilled price + fundamentals layer seeded via the openbb
MCP (see Datasets/History/README.md). This script keeps it current by fetching only the DELTA — it reads
the last stored date per ticker and asks yfinance for everything after it. Never rewrites history, only
appends. Safe to run weekly.

Layout it maintains (all under Datasets/History/):
    prices_monthly/<TICKER>.csv      date,open,high,low,close,volume,split_ratio,dividend,symbol
    prices_daily/<TICKER>.csv        same shape, daily
    fundamentals_annual/<TICKER>.csv period,currency,revenue,net_income,eps,operating_income,...
    fundamentals_quarterly/<TICKER>.csv
    MANIFEST.csv                     series,ticker,rows,first,last,source,file
"""
import argparse, csv, datetime as dt, glob, os, re, sys, traceback

VAULT = os.path.expanduser("~/Documents/Finance Knowledge Graph")
HIST = os.path.join(VAULT, "Datasets", "History")
BENCH = ["SPY", "QQQ", "IWM", "SOXX", "SMH", "SOXL", "TQQQ", "XLK", "XLE", "XLV", "XLF",
         "TLT", "GLD", "DBA", "UUP", "RSP", "VTV", "URA", "LIT"]


def universe():
    """Every company node's ticker, plus benchmarks."""
    tk = set()
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
            m = re.search(r'ticker:\s*"?([A-Za-z0-9.\-]+)"?', txt.split("---", 2)[1])
            if m and m.group(1):
                tk.add(m.group(1).upper())
        except Exception:
            pass
    return sorted(tk | set(BENCH))


def last_date(path, col="date"):
    if not os.path.exists(path):
        return None
    rows = list(csv.DictReader(open(path)))
    return rows[-1][col] if rows else None


def append_rows(path, rows, cols):
    """Merge by date; never duplicate, never rewrite existing values."""
    old = {}
    if os.path.exists(path):
        for r in csv.DictReader(open(path)):
            old[str(r.get("date", ""))] = r
    for r in rows:
        old[str(r["date"])] = r
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows([old[k] for k in sorted(old) if k])


def sync_prices(tickers, kinds=("monthly", "daily")):
    import yfinance as yf
    today = dt.date.today()
    for tk in tickers:
        for kind in kinds:
            path = os.path.join(HIST, f"prices_{kind}", f"{tk}.csv")
            last = last_date(path)
            if kind == "monthly":
                start = "2000-01-01" if not last else (
                    (dt.date.fromisoformat(last[:10]) - dt.timedelta(days=5)).isoformat())
                interval = "1mo"
            else:
                start = "2015-01-01" if not last else (
                    (dt.date.fromisoformat(last[:10]) - dt.timedelta(days=5)).isoformat())
                interval = "1d"
            if last and dt.date.fromisoformat(last[:10]) >= today - dt.timedelta(days=1):
                continue
            try:
                df = yf.Ticker(tk).history(start=start, interval=interval,
                                           auto_adjust=False, actions=True)
                if df is None or df.empty:
                    print(f"  {kind:7s} {tk:8s} no data"); continue
                rows = []
                for idx, r in df.iterrows():
                    d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
                    rows.append({"date": d, "open": r.get("Open"), "high": r.get("High"),
                                 "low": r.get("Low"), "close": r.get("Close"),
                                 "volume": r.get("Volume"),
                                 "split_ratio": r.get("Stock Splits", ""), "dividend": r.get("Dividends", ""),
                                 "symbol": tk})
                append_rows(path, rows, list(rows[0].keys()))
                print(f"  {kind:7s} {tk:8s} +{len(rows):5d} -> {last_date(path)}")
            except Exception as e:
                print(f"  {kind:7s} {tk:8s} FAILED: {e}")


def sync_fundamentals(tickers):
    """Annual + quarterly statements via yfinance (USD-consistent, unlike raw XBRL across filers)."""
    import yfinance as yf
    for tk in tickers:
        try:
            t = yf.Ticker(tk)
            for freq, obj in (("annual", t.financials), ("quarterly", t.quarterly_financials)):
                if obj is None or obj.empty:
                    continue
                path = os.path.join(HIST, f"fundamentals_{freq}", f"{tk}.csv")
                cols = ["period"] + [str(c)[:10] for c in obj.columns]
                rows = []
                for label in obj.index:
                    vals = [obj.loc[label, c] for c in obj.columns]
                    if all(v != v for v in vals):   # all NaN
                        continue
                    rows.append({"metric": str(label), **{str(c)[:10]: ("" if v != v else v)
                                                          for c, v in zip(obj.columns, vals)}})
                if not rows:
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["metric"] + cols[1:], extrasaction="ignore")
                    w.writeheader(); w.writerows(rows)
                print(f"  fundamentals/{freq} {tk:8s} {len(rows)} metrics x {len(obj.columns)} periods")
        except Exception as e:
            print(f"  fundamentals {tk:8s} FAILED: {e}")
            traceback.print_exc(limit=1)


def rebuild_manifest():
    rows = []
    for d in ("prices_monthly", "prices_daily", "fundamentals_annual", "fundamentals_quarterly"):
        for p in sorted(glob.glob(os.path.join(HIST, d, "*.csv"))):
            rd = list(csv.DictReader(open(p)))
            if not rd:
                continue
            first = rd[0].get("date") or rd[0].get("period") or rd[0].get("metric") or ""
            last = rd[-1].get("date") or rd[-1].get("period") or rd[-1].get("metric") or ""
            rows.append({"series": d, "ticker": os.path.basename(p)[:-4], "rows": len(rd),
                         "first": first, "last": last,
                         "source": "yfinance+openbb" if d.startswith("prices") else "yfinance",
                         "file": f"{d}/{os.path.basename(p)}"})
    out = os.path.join(HIST, "MANIFEST.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["series", "ticker", "rows", "first", "last", "source", "file"])
        w.writeheader(); w.writerows(rows)
    print(f"\nMANIFEST.csv rebuilt: {len(rows)} series")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", action="store_true")
    ap.add_argument("--fundamentals", action="store_true")
    ap.add_argument("--monthly-only", action="store_true", help="with --prices: skip the daily set")
    ap.add_argument("--tickers", help="comma list to restrict to")
    a = ap.parse_args()
    tks = a.tickers.split(",") if a.tickers else universe()
    print(f"universe: {len(tks)} tickers")
    if a.prices:
        sync_prices(tks, ("monthly",) if a.monthly_only else ("monthly", "daily"))
    if a.fundamentals:
        sync_fundamentals(tks)
    rebuild_manifest()
