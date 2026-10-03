#!/usr/bin/env python3
"""Analyze VIX term structure and classify volatility regime.

Usage: python3 volatility_regime.py
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Volatility-Regime.md
"""
import os, sys
from datetime import date
from yahoo_guard import raise_if_yahoo_rate_limit

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except Exception as e:
    print(f"FATAL: need yfinance/pandas/numpy: {e}")
    sys.exit(1)

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")


def fetch_vol_data():
    result = {}
    try:
        vix = yf.Ticker("^VIX").history(period="1y")["Close"]
        if not vix.empty:
            result["vix_current"] = round(vix.iloc[-1], 2)
            result["vix_30d_avg"] = round(vix.iloc[-22:].mean(), 2) if len(vix) > 22 else round(vix.mean(), 2)
            result["vix_percentile"] = round((vix < vix.iloc[-1]).sum() / len(vix) * 100, 1)
    except Exception as exc:
        raise_if_yahoo_rate_limit(exc, "VIX volatility fetch")
        pass
    try:
        # Historical vol (20-day realized)
        spy = yf.Ticker("SPY").history(period="3mo")["Close"]
        if len(spy) > 20:
            returns = np.log(spy / spy.shift(1)).dropna()
            hist_vol = returns.iloc[-20:].std() * np.sqrt(252) * 100
            result["realized_vol_20d"] = round(hist_vol, 2)
    except Exception as exc:
        raise_if_yahoo_rate_limit(exc, "SPY realized-volatility fetch")
        pass
    return result


def classify(data):
    vix = data.get("vix_current", 20)
    if vix < 12:
        return "VERY LOW", "Complacency — potential for vol expansion"
    elif vix < 16:
        return "LOW", "Calm markets — carry-friendly"
    elif vix < 22:
        return "NORMAL", "Balanced risk environment"
    elif vix < 30:
        return "ELEVATED", "Caution warranted — hedging recommended"
    elif vix < 40:
        return "HIGH", "Stress — defensive positioning"
    else:
        return "EXTREME", "Crisis mode — tail risk elevated"


def write_note(today, data, regime, description):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "market-context"',
        f'date: "{today}"',
        'topic: "Volatility regime assessment"',
        'tags: ["macro", "volatility", "VIX"]',
        "---",
        "",
        f"# Volatility Regime — {today}",
        "",
        f"**Regime: {regime}**",
        f"> {description}",
        "",
    ]
    for k, v in data.items():
        lines.append(f"- {k}: **{v}**")
    lines.append("")
    path = os.path.join(KG_NOTES, f"{today} Volatility-Regime.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    today = date.today().isoformat()
    data = fetch_vol_data()
    regime, desc = classify(data)
    write_note(today, data, regime, desc)
    print(f"Regime: {regime}")


if __name__ == "__main__":
    main()
