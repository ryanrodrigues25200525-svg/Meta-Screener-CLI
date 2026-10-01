#!/usr/bin/env python3
"""Fetch short interest data for portfolio holdings.

Usage: python3 short_interest.py [--tickers TICKER1,TICKER2]
Reads: ~/finance-ai/pm_portfolio.json
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Short-Interest.md
"""
import os, sys, json
from datetime import date
from yahoo_guard import raise_if_yahoo_rate_limit

try:
    import yfinance as yf
except Exception as e:
    print(f"FATAL: need yfinance: {e}")
    sys.exit(1)

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
PM_FILE = os.path.expanduser("~/finance-ai/pm_portfolio.json")


def load_holdings():
    try:
        with open(PM_FILE) as f:
            data = json.load(f)
        return [h.get("ticker") or h.get("symbol") for h in data.get("positions", [])]
    except Exception:
        return []


def fetch_short_interest(tickers):
    results = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            si = info.get("shortRatio") or info.get("shortPercentOfFloat")
            si_pct = info.get("shortPercentOfFloat", 0) or 0
            si_ratio = info.get("shortRatio", 0) or 0
            shares_short = info.get("sharesShort", 0) or 0
            results.append({
                "ticker": ticker,
                "short_pct": round(si_pct * 100, 2) if si_pct else 0,
                "short_ratio": round(si_ratio, 2) if si_ratio else 0,
                "shares_short": shares_short,
                "flag": "HIGH" if si_pct and si_pct > 0.20 else "ELEVATED" if si_pct and si_pct > 0.10 else "NORMAL",
            })
        except Exception as exc:
            raise_if_yahoo_rate_limit(exc, f"short-interest fetch for {ticker}")
            pass
    return results


def write_note(today, data):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        'topic: "Short interest scan — portfolio holdings"',
        'tags: ["short-interest", "sentiment"]',
        "---",
        "",
        f"# Short Interest Scan — {today}",
        "",
        "| Ticker | Short % Float | Days to Cover | Shares Short | Flag |",
        "|--------|---------------|---------------|--------------|------|",
    ]
    for d in sorted(data, key=lambda x: x["short_pct"], reverse=True):
        shares = f'{d["shares_short"]:,}' if d["shares_short"] else "N/A"
        lines.append(f"| {d['ticker']} | {d['short_pct']}% | {d['short_ratio']} | {shares} | {d['flag']} |")
    flagged = [d["ticker"] for d in data if d["flag"] in ("HIGH", "ELEVATED")]
    if flagged:
        lines.extend(["", f"**⚠️ Flagged:** {', '.join(flagged)}"])
    path = os.path.join(KG_NOTES, f"{today} Short-Interest.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=str, default=None)
    args = ap.parse_args()
    today = date.today().isoformat()
    tickers = args.tickers.split(",") if args.tickers else load_holdings()
    if not tickers:
        print("No tickers found. Use --tickers or add pm_portfolio.json")
        return
    data = fetch_short_interest(tickers)
    write_note(today, data)
    print(f"Scanned {len(data)} tickers")


if __name__ == "__main__":
    main()
