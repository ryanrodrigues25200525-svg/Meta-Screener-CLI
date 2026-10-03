#!/usr/bin/env python3
"""Analyze sector ETF performance for rotation signals.

Usage: python3 sector_rotation.py
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Sector-Rotation.md
"""
import os, sys, argparse
from datetime import date
from yahoo_guard import raise_if_yahoo_rate_limit

try:
    import yfinance as yf
    import pandas as pd
except Exception as e:
    print(f"FATAL: need yfinance/pandas: {e}")
    sys.exit(1)

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")

SECTORS = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Health Care", "XLI": "Industrials", "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLB": "Materials", "XLC": "Communication Services",
}


def fetch_returns():
    results = {}
    for ticker, name in SECTORS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="3mo")
            if hist.empty or len(hist) < 5:
                continue
            last = hist["Close"].iloc[-1]
            ret_1w = (last / hist["Close"].iloc[-5] - 1) * 100 if len(hist) >= 5 else 0
            ret_1m = (last / hist["Close"].iloc[-22] - 1) * 100 if len(hist) >= 22 else 0
            ret_3m = (last / hist["Close"].iloc[0] - 1) * 100
            results[name] = {"ticker": ticker, "1w": round(ret_1w, 2), "1m": round(ret_1m, 2), "3m": round(ret_3m, 2)}
        except Exception as exc:
            raise_if_yahoo_rate_limit(exc, f"sector ETF fetch for {ticker}")
            pass
    return results


def write_note(today, data):
    os.makedirs(KG_NOTES, exist_ok=True)
    sorted_1m = sorted(data.items(), key=lambda x: x[1]["1m"], reverse=True)
    lines = [
        "---",
        'type: "market-context"',
        f'date: "{today}"',
        'topic: "Sector rotation analysis"',
        'tags: ["macro", "sector-rotation"]',
        "---",
        "",
        f"# Sector Rotation — {today}",
        "",
        "| Sector | Ticker | 1w % | 1m % | 3m % |",
        "|--------|--------|------|------|------|",
    ]
    for name, d in sorted_1m:
        lines.append(f"| {name} | {d['ticker']} | {d['1w']}% | {d['1m']}% | {d['3m']}% |")
    leaders = [n for n, d in sorted_1m[:3]]
    laggards = [n for n, d in sorted_1m[-3:]]
    lines.extend(["", f"**Leaders (1m):** {', '.join(leaders)}", f"**Laggards (1m):** {', '.join(laggards)}", ""])
    path = os.path.join(KG_NOTES, f"{today} Sector-Rotation.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    today = date.today().isoformat()
    data = fetch_returns()
    write_note(today, data)
    print(f"Fetched {len(data)} sectors")


if __name__ == "__main__":
    main()
