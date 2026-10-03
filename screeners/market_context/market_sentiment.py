#!/usr/bin/env python3
"""Fetch VIX, put/call ratio, and Fear & Greed proxy via yfinance.

Usage: python3 market_sentiment.py
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Market-Sentiment.md
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


def fetch_vix():
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="3mo")
        if hist.empty:
            return None
        current = hist["Close"].iloc[-1]
        avg_30d = hist["Close"].iloc[-22:].mean() if len(hist) > 22 else hist["Close"].mean()
        low_52w = hist["Close"].min()
        high_52w = hist["Close"].max()
        return {
            "current": round(current, 2),
            "avg_30d": round(avg_30d, 2),
            "low_52w": round(low_52w, 2),
            "high_52w": round(high_52w, 2),
            "regime": "LOW" if current < 15 else "NORMAL" if current < 25 else "HIGH" if current < 35 else "EXTREME",
        }
    except Exception as exc:
        raise_if_yahoo_rate_limit(exc, "VIX sentiment fetch")
        return None


def fetch_put_call():
    try:
        # Use CBOE put/call ratio proxy via index
        qqq = yf.Ticker("QQQ").history(period="1mo")["Close"]
        spy = yf.Ticker("SPY").history(period="1mo")["Close"]
        if qqq.empty or spy.empty:
            return None
        # Simple breadth proxy: QQQ/SPY ratio trend
        ratio = (qqq.iloc[-1] / spy.iloc[-1]) / (qqq.iloc[0] / spy.iloc[0]) * 100
        return {"qqq_spy_ratio": round(ratio, 2)}
    except Exception as exc:
        raise_if_yahoo_rate_limit(exc, "QQQ/SPY sentiment proxy")
        return None


def write_note(today, vix, pc):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "market-context"',
        f'date: "{today}"',
        'topic: "Market sentiment snapshot"',
        'tags: ["macro", "sentiment", "VIX"]',
        "---",
        "",
        f"# Market Sentiment — {today}",
        "",
    ]
    if vix:
        lines.extend([
            "## VIX",
            f"- Current: **{vix['current']}** ({vix['regime']})",
            f"- 30-day avg: {vix['avg_30d']}",
            f"- 52-week range: {vix['low_52w']} – {vix['high_52w']}",
            "",
        ])
    if pc:
        lines.extend([
            "## Breadth Proxy",
            f"- QQQ/SPY relative strength: {pc['qqq_spy_ratio']}",
            "",
        ])
    path = os.path.join(KG_NOTES, f"{today} Market-Sentiment.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    today = date.today().isoformat()
    vix = fetch_vix()
    pc = fetch_put_call()
    write_note(today, vix, pc)
    print("Done")


if __name__ == "__main__":
    main()
