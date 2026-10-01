#!/usr/bin/env python3
"""Analyze dividend yields for portfolio holdings.

Usage: python3 dividend_analysis.py
Reads: ~/finance-ai/pm_portfolio.json
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Dividend-Analysis.md
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
        with open(PM_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [h.get("symbol") or h.get("ticker") for h in data.get("positions", []) if h.get("symbol") or h.get("ticker")]
    except Exception:
        return []


def analyze(tickers):
    results = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            div_yield = info.get("dividendYield", 0) or 0
            div_rate = info.get("dividendRate", 0) or 0
            if div_yield and div_yield > 1:  # yfinance already in percent for many tickers
                div_yield = div_yield / 100
            # cross-check: prefer rate/price (yfinance mixes ratio vs percent across tickers)
            _px = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            if div_rate and _px:
                _ry = div_rate / _px
                if _ry and abs(_ry - div_yield) > 0.05:  # >5pp disagreement -> trust rate/price
                    div_yield = _ry
            payout = info.get("payoutRatio", 0) or 0
            ex_date = info.get("exDividendDate")
            results.append({
                "ticker": ticker,
                "yield": round(div_yield * 100, 2),
                "rate": round(div_rate, 2),
                "payout": round(payout * 100, 1) if payout else None,
            })
        except Exception as exc:
            raise_if_yahoo_rate_limit(exc, f"dividend fetch for {ticker}")
            pass
    return results


def write_note(today, data):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        'topic: "Dividend analysis — portfolio holdings"',
        'tags: ["dividend", "income"]',
        "---",
        "",
        f"# Dividend Analysis — {today}",
        "",
        "| Ticker | Yield % | Annual $/share | Payout % |",
        "|--------|---------|----------------|----------|",
    ]
    for d in sorted(data, key=lambda x: x["yield"], reverse=True):
        payout = f'{d["payout"]}%' if d["payout"] else "N/A"
        lines.append(f"| {d['ticker']} | {d['yield']}% | ${d['rate']} | {payout} |")
    path = os.path.join(KG_NOTES, f"{today} Dividend-Analysis.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    import argparse as _ap
    _p = _ap.ArgumentParser()
    _p.add_argument("--income-portfolio", action="store_true", help="limit to dividend-paying portfolio names")
    _a, _ = _p.parse_known_args()
    today = date.today().isoformat()
    tickers = load_holdings()
    income_only = _a.income_portfolio
    if not tickers:
        tickers = ["VZ", "JNJ", "KO", "PG", "MMM", "T", "XOM", "CVX"]
        print("No pm_portfolio.json found, using default dividend stocks")
    data = analyze(tickers)
    if income_only:
        data = [r for r in data if r["yield"] > 0]
    write_note(today, data)
    print(f"Analyzed {len(data)} tickers")


if __name__ == "__main__":
    main()
