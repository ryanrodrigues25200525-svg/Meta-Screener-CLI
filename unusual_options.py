#!/usr/bin/env python3
"""Check unusual options activity for portfolio holdings.

Usage: python3 unusual_options.py [--tickers TICKER1,TICKER2] [--batch]
Reads: ~/finance-ai/pm_portfolio.json
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Unusual-Options.md
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


def check_options(ticker):
    try:
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return None
        # Check nearest expiration
        chains = t.option_chain(expirations[0])
        calls = chains.calls
        puts = chains.puts
        total_call_vol = calls["volume"].sum() if not calls.empty else 0
        total_put_vol = puts["volume"].sum() if not puts.empty else 0
        total_call_oi = calls["openInterest"].sum() if not calls.empty else 0
        total_put_oi = puts["openInterest"].sum() if not puts.empty else 0
        pc_ratio = total_put_vol / total_call_vol if total_call_vol > 0 else 0
        # Unusual: volume > 2x OI
        unusual_calls = calls[calls["volume"] > calls["openInterest"] * 2] if not calls.empty else []
        unusual_puts = puts[puts["volume"] > puts["openInterest"] * 2] if not puts.empty else []
        return {
            "ticker": ticker,
            "expiry": expirations[0],
            "call_vol": int(total_call_vol),
            "put_vol": int(total_put_vol),
            "pc_ratio": round(pc_ratio, 2),
            "unusual_calls": len(unusual_calls),
            "unusual_puts": len(unusual_puts),
            "flag": "UNUSUAL" if len(unusual_calls) > 0 or len(unusual_puts) > 0 else "NORMAL",
        }
    except Exception as exc:
        raise_if_yahoo_rate_limit(exc, f"options fetch for {ticker}")
        return None


def write_note(today, data):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        'topic: "Unusual options activity scan"',
        'tags: ["options", "sentiment"]',
        "---",
        "",
        f"# Unusual Options Activity — {today}",
        "",
        "| Ticker | Expiry | Call Vol | Put Vol | P/C Ratio | Unusual Calls | Unusual Puts | Flag |",
        "|--------|--------|----------|---------|-----------|---------------|--------------|------|",
    ]
    for d in data:
        lines.append(f"| {d['ticker']} | {d['expiry']} | {d['call_vol']:,} | {d['put_vol']:,} | {d['pc_ratio']} | {d['unusual_calls']} | {d['unusual_puts']} | {d['flag']} |")
    flagged = [d["ticker"] for d in data if d["flag"] == "UNUSUAL"]
    if flagged:
        lines.extend(["", f"**⚠️ Unusual activity:** {', '.join(flagged)}"])
    path = os.path.join(KG_NOTES, f"{today} Unusual-Options.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=str, default=None)
    ap.add_argument("--batch", action="store_true")
    args = ap.parse_args()
    today = date.today().isoformat()
    tickers = args.tickers.split(",") if args.tickers else load_holdings()
    if not tickers:
        print("No tickers found. Use --tickers or add pm_portfolio.json")
        return
    results = []
    for ticker in tickers:
        r = check_options(ticker)
        if r:
            results.append(r)
    write_note(today, results)
    print(f"Scanned {len(results)} tickers")


if __name__ == "__main__":
    main()
