#!/usr/bin/env python3
"""Analyze dividend yields from Yahoo Finance.

Yahoo-backed: yield, rate, and payout fields come from Yahoo Finance
``info`` via ``yahoo_client`` (the only allowed Yahoo path — never call
``yf.Ticker`` directly). The ticker list is an explicit ``--tickers``
selection or the shared built-in universe; nothing is read from local
portfolio files.

Usage:
    python3 dividend_analysis.py [--tickers VZ,JNJ] [--income-portfolio]
        [--result-json out/dividend.json]
"""

import argparse
import json
import os
import tempfile
from datetime import date

from demo_universe import HOLDINGS_TICKERS


def _default_notes_dir():
    override = os.environ.get("SCREEN_NOTES_DIR")
    if override:
        return override
    legacy = os.environ.get("FINANCE_KG_ROOT")
    if legacy:
        return os.path.join(legacy, "Notes")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


NOTES_DIR = _default_notes_dir()


def default_tickers():
    """Shared built-in universe (selection input only)."""
    return list(HOLDINGS_TICKERS)


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_info"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_info, or a provider callable")


def _safe_info(client, ticker):
    """Yahoo info for one ticker; None when unavailable.

    Rate-limit RuntimeErrors propagate (fail fast); per-ticker gaps are blank.
    """
    try:
        return client.get_info(ticker)
    except RuntimeError:
        raise
    except Exception:
        return None


def analyze(tickers, provider=None):
    """Yahoo dividend rows for each ticker. One row per ticker."""
    client = _client_for(provider)
    results = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        info = _safe_info(client, ticker)
        if not info:
            results.append({"ticker": ticker, "blank": True})
            continue
        try:
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
        except AttributeError:
            results.append({"ticker": ticker, "blank": True})
            continue
        results.append({
            "ticker": ticker,
            "yield": round(div_yield * 100, 2),
            "rate": round(div_rate, 2),
            "payout": round(payout * 100, 1) if payout else None,
        })
    return results


def screen_tickers(tickers, provider=None):
    """Dividend rows for the given tickers, fetched via Yahoo only."""
    return analyze(tickers, provider=provider)


def build_result_payload(data, report_path):
    measured = [r for r in data if not r.get("blank")]
    blanks = [r for r in data if r.get("blank")]
    ranked = sorted(measured, key=lambda row: row.get("yield") or 0, reverse=True)
    top = []
    for rank, row in enumerate(ranked, 1):
        payout = "n/a" if row.get("payout") is None else f"{row['payout']}%"
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"Yield {row.get('yield') or 0}%; annual rate ${row.get('rate') or 0}; payout {payout}",
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no Yahoo dividend info for {row['ticker']}",
        })
    return {
        "summary": (f"{len(ranked)} names with Yahoo dividend info "
                    f"({len(blanks)} blank)"),
        "report_path": str(report_path),
        "top": top,
    }


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path),
            prefix=".dividend-analysis-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def write_note(today, data, result_json_path=None, notes_dir=None):
    notes_dir = notes_dir or NOTES_DIR
    os.makedirs(notes_dir, exist_ok=True)
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        'topic: "Dividend analysis — Yahoo yield and payout fields"',
        'tags: ["dividend", "income"]',
        "---",
        "",
        f"# Dividend Analysis (Yahoo) — {today}",
        "",
        "| Ticker | Yield % | Annual $/share | Payout % |",
        "|--------|---------|----------------|----------|",
    ]
    ranked = sorted([d for d in data if not d.get("blank")],
                    key=lambda x: x.get("yield") or 0, reverse=True)
    for d in ranked:
        payout = f'{d["payout"]}%' if d.get("payout") else "N/A"
        lines.append(f"| {d['ticker']} | {d.get('yield', 0)}% | ${d.get('rate', 0)} | {payout} |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | | |")
    path = os.path.join(notes_dir, f"{today} Dividend-Analysis.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {path}")
    if result_json_path:
        write_result_json(result_json_path, build_result_payload(data, path))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=str, default=None,
                    help="comma-separated symbols; default: built-in universe")
    ap.add_argument("--income-portfolio", action="store_true", help="limit to dividend-paying names")
    ap.add_argument("--result-json", help="write the ranked rows for the CLI dashboard")
    args = ap.parse_args(argv)
    today = date.today().isoformat()
    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
               if args.tickers else default_tickers())
    data = analyze(tickers)
    if args.income_portfolio:
        data = [r for r in data if (r.get("yield") or 0) > 0]
    write_note(today, data, args.result_json)
    print(f"Analyzed {len(data)} tickers")


if __name__ == "__main__":
    main()
