#!/usr/bin/env python3
"""Rank cash returns (FCF yield plus buyback yield) from Yahoo Finance.

Yahoo-backed: free cash flow and share repurchases come from Yahoo annual
cashflow statements and market cap from Yahoo info, all via
``yahoo_client`` (the only allowed Yahoo path — never call ``yf.Ticker``
directly). Missing data stays blank.

Usage:
    python3 cash_return.py [--tickers AAPL,MSFT] [--result-json out/cash.json]
"""

import argparse
import json
import math
import os
import tempfile
from datetime import date

from demo_universe import HOLDINGS_TICKERS


def _default_notes_dir():
    override = os.environ.get("SCREEN_NOTES_DIR")
    if override:
        return override
    legacy = os.environ.get("FINANCE_AI_ROOT") or os.environ.get("FINANCE_KG_ROOT")
    if legacy:
        return os.path.join(legacy, "Notes")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


NOTES_DIR = _default_notes_dir()


def default_tickers():
    """Shared built-in universe (selection input only)."""
    return list(HOLDINGS_TICKERS)


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_financials"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_financials, or a provider callable")


def _latest(frame, *names):
    """Latest annual value for the first matching row label; None when unusable."""
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        index = [str(i) for i in frame.index]
    except Exception:
        return None
    lowered = {name.lower(): name for name in index}
    for wanted in names:
        if wanted.lower() in lowered:
            try:
                value = float(frame.loc[lowered[wanted.lower()]].iloc[0])
            except (TypeError, ValueError, IndexError, KeyError):
                return None
            if math.isnan(value):
                return None
            return value
    return None


def screen_tickers(tickers, provider=None):
    """Cash-return rows for the given tickers, fetched via Yahoo only."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        try:
            cashflow = client.get_financials(ticker, kind="cashflow")
            info = client.get_info(ticker) or {}
        except RuntimeError:
            raise
        except Exception:
            rows.append({"ticker": ticker, "blank": True})
            continue
        fcf = _latest(cashflow, "Free Cash Flow")
        spent = _latest(cashflow, "Repurchase Of Capital Stock",
                        "Repurchase Of Common Stock")
        cap = info.get("marketCap")
        if fcf is None or not cap or cap <= 0:
            rows.append({"ticker": ticker, "blank": True})
            continue
        # Yahoo books repurchases as a negative cash outflow; yield is positive.
        buyback = -(spent or 0)
        rows.append({
            "ticker": ticker,
            "fcf_yield": round(fcf / cap * 100, 2),
            "buyback_yield": round(buyback / cap * 100, 2),
        })
    return rows


def build_result_payload(data, report_path):
    measured = [r for r in data if not r.get("blank")]
    blanks = [r for r in data if r.get("blank")]
    ranked = sorted(measured, key=lambda row: row.get("fcf_yield") or 0, reverse=True)
    top = []
    for rank, row in enumerate(ranked, 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (f"FCF yield {row['fcf_yield']}%; "
                       f"buyback {row['buyback_yield']}%"),
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no usable Yahoo cashflow for {row['ticker']}",
        })
    return {
        "summary": (f"{len(ranked)} names with Yahoo cash returns "
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
            prefix=".cash-return-", suffix=".tmp", delete=False,
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
        'topic: "Cash return — Yahoo FCF and buyback yields"',
        'tags: ["cash", "buyback", "yield"]',
        "---",
        "",
        f"# Cash Return (Yahoo) — {today}",
        "",
        "| Ticker | FCF % | Buyback % |",
        "|--------|-------|-----------|",
    ]
    ranked = sorted([d for d in data if not d.get("blank")],
                    key=lambda x: x.get("fcf_yield") or 0, reverse=True)
    for d in ranked:
        lines.append(f"| {d['ticker']} | {d['fcf_yield']}% | {d['buyback_yield']}% |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | |")
    path = os.path.join(notes_dir, f"{today} Cash-Return.md")
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
    ap.add_argument("--result-json", help="write the ranked rows for the CLI dashboard")
    args = ap.parse_args(argv)
    today = date.today().isoformat()
    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
               if args.tickers else default_tickers())
    data = screen_tickers(tickers)
    ranked = [d for d in data if not d.get("blank")]
    blanks = [d for d in data if d.get("blank")]
    print(f"Cash returns for {len(ranked)} of {len(tickers)} tickers; {len(blanks)} blank")
    for row in sorted(ranked, key=lambda r: r.get("fcf_yield") or 0, reverse=True)[:10]:
        print(f"  {row['ticker']:6} FCF {row['fcf_yield']}% buyback {row['buyback_yield']}%")
    for row in blanks:
        print(f"  {row['ticker']:6} blank — no usable Yahoo cashflow")
    write_note(today, data, args.result_json)


if __name__ == "__main__":
    main()
