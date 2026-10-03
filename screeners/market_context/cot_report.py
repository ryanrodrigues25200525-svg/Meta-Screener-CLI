#!/usr/bin/env python3
"""Fetch COT (Commitments of Traders) positioning data.

Usage: python3 cot_report.py
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> COT-Report.md

Note: COT data from CFTC is weekly. This fetches futures positioning via yfinance proxy.
"""
import os, sys
from datetime import date
from yahoo_guard import raise_if_yahoo_rate_limit

try:
    import yfinance as yf
    import pandas as pd
except Exception as e:
    print(f"FATAL: need yfinance/pandas: {e}")
    sys.exit(1)

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")

# Major futures contracts as COT proxy
FUTURES = {
    "ES=F": "S&P 500 E-mini",
    "NQ=F": "Nasdaq E-mini",
    "YM=F": "Dow E-mini",
    "GC=F": "Gold",
    "SI=F": "Silver",
    "CL=F": "Crude Oil",
    "ZB=F": "US Treasury Bond",
    "ZN=F": "10-Year T-Note",
    "DX=F": "US Dollar Index",
}


def fetch_positioning():
    results = {}
    for ticker, name in FUTURES.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="3mo")
            if hist.empty:
                continue
            last = hist["Close"].iloc[-1]
            high = hist["Close"].max()
            low = hist["Close"].min()
            pct_from_high = (last / high - 1) * 100
            pct_from_low = (last / low - 1) * 100
            # Simple positioning proxy: where in range
            if high != low:
                position_in_range = (last - low) / (high - low) * 100
            else:
                position_in_range = 50
            results[name] = {
                "price": round(last, 2),
                "from_high": round(pct_from_high, 1),
                "from_low": round(pct_from_low, 1),
                "range_pct": round(position_in_range, 0),
            }
        except Exception as exc:
            raise_if_yahoo_rate_limit(exc, f"futures proxy fetch for {ticker}")
            pass
    return results


def write_note(today, data):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "market-context"',
        f'date: "{today}"',
        'topic: "COT / futures positioning proxy"',
        'tags: ["macro", "futures", "positioning"]',
        "---",
        "",
        f"# Futures Positioning (COT Proxy) — {today}",
        "",
        "| Contract | Price | From High | From Low | Range % |",
        "|----------|-------|-----------|----------|---------|",
    ]
    for name, d in sorted(data.items()):
        lines.append(f"| {name} | {d['price']} | {d['from_high']}% | {d['from_low']}% | {d['range_pct']}% |")
    lines.append("")
    lines.append("> Positioning is proxied by 3-month range. For actual COT data, use CFTC reports.")
    path = os.path.join(KG_NOTES, f"{today} COT-Report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    today = date.today().isoformat()
    data = fetch_positioning()
    write_note(today, data)
    print(f"Fetched {len(data)} contracts")


if __name__ == "__main__":
    main()
