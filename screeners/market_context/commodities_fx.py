#!/usr/bin/env python3
"""Fetch commodity prices and FX rates via yfinance.

Usage: python3 commodities_fx.py
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Commodities-FX.md
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

COMMODITIES = {
    "GC=F": "Gold", "SI=F": "Silver", "HG=F": "Copper",
    "CL=F": "WTI Crude", "BZ=F": "Brent Crude", "NG=F": "Natural Gas",
}
FX = {
    "DX-Y.NYB": "DXY (US Dollar Index)",
    "EURUSD=X": "EUR/USD", "JPY=X": "USD/JPY",
    "GBPUSD=X": "GBP/USD", "CNY=X": "USD/CNY",
}


def fetch(tickers, period="3mo"):
    data = {}
    for ticker, name in {**COMMODITIES, **FX}.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if hist.empty:
                continue
            last = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-21] if len(hist) > 21 else hist["Close"].iloc[0]
            chg_1d = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100 if len(hist) > 1 else 0
            chg_1m = (last / prev - 1) * 100
            data[name] = {"price": round(last, 2), "1d%": round(chg_1d, 2), "1m%": round(chg_1m, 2)}
        except Exception as exc:
            raise_if_yahoo_rate_limit(exc, f"commodity/FX fetch for {ticker}")
            pass
    return data


def write_note(today, data):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "market-context"',
        f'date: "{today}"',
        'topic: "Commodities & FX snapshot"',
        'tags: ["macro", "commodities", "fx"]',
        "---",
        "",
        f"# Commodities & FX — {today}",
        "",
        "| Asset | Price | 1d % | 1m % |",
        "|-------|-------|------|------|",
    ]
    for name, d in data.items():
        lines.append(f"| {name} | {d['price']} | {d['1d%']}% | {d['1m%']}% |")
    lines.append("")
    path = os.path.join(KG_NOTES, f"{today} Commodities-FX.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="3mo")
    args = ap.parse_args()
    today = date.today().isoformat()
    data = fetch(list(COMMODITIES.keys()) + list(FX.keys()), period=args.period)
    write_note(today, data)
    print(f"Fetched {len(data)} assets")


if __name__ == "__main__":
    main()
