#!/usr/bin/env python3
"""Rank Altman Z-scores from Yahoo Finance statements.

Yahoo-backed: EBIT, revenue, working capital, retained earnings, assets,
and liabilities come from Yahoo annual statements and market cap from
Yahoo info, all via ``yahoo_client`` (the only allowed Yahoo path — never
call ``yf.Ticker`` directly). Missing or mismatched data stays blank.

Z = 1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*MVE/TL + 1.0*Sales/TA.
Zones: >2.99 safe, 1.81-2.99 grey, <1.81 distress.

Usage:
    python3 altman_z.py [--tickers AAPL,MSFT] [--result-json out/altman.json]
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


def _z_score(income, balance, market_cap):
    """Altman Z from annual statements; None when inputs are missing."""
    ebit = _latest(income, "EBIT")
    sales = _latest(income, "Total Revenue", "Operating Revenue")
    wc = _latest(balance, "Working Capital")
    re = _latest(balance, "Retained Earnings")
    ta = _latest(balance, "Total Assets")
    tl = _latest(balance, "Total Liabilities Net Minority Interest",
                 "Total Liab", "Total Liabilities")
    if None in (ebit, sales, wc, re, ta, tl):
        return None
    if not ta or not tl or market_cap is None or market_cap <= 0:
        return None
    try:
        z = (1.2 * wc / ta + 1.4 * re / ta + 3.3 * ebit / ta
             + 0.6 * market_cap / tl + 1.0 * sales / ta)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if math.isnan(z):
        return None
    return round(z, 2)


def _zone(z):
    if z > 2.99:
        return "safe"
    if z >= 1.81:
        return "grey"
    return "distress"


def screen_tickers(tickers, provider=None):
    """Altman-Z rows for the given tickers, fetched via Yahoo only."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        try:
            income = client.get_financials(ticker, kind="income")
            balance = client.get_financials(ticker, kind="balance")
            info = client.get_info(ticker) or {}
        except RuntimeError:
            raise
        except Exception:
            rows.append({"ticker": ticker, "blank": True})
            continue
        z = _z_score(income, balance, info.get("marketCap"))
        if z is None:
            rows.append({"ticker": ticker, "blank": True})
            continue
        rows.append({"ticker": ticker, "z": z, "zone": _zone(z)})
    return rows


def build_result_payload(data, report_path):
    measured = [r for r in data if not r.get("blank")]
    blanks = [r for r in data if r.get("blank")]
    ranked = sorted(measured, key=lambda row: row.get("z") if row.get("z") is not None else -99,
                    reverse=True)
    top = []
    for rank, row in enumerate(ranked, 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"Z {row['z']} ({row['zone']} zone)",
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no usable Yahoo statements for {row['ticker']}",
        })
    # Attach numeric z for tests/consumers without changing the validated shape.
    for row in top:
        src = next((m for m in measured if m["ticker"] == row["ticker"]), None)
        if src is not None:
            row["z"] = src["z"]
    return {
        "summary": (f"{len(ranked)} names with Yahoo Altman-Z "
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
            prefix=".altman-z-", suffix=".tmp", delete=False,
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
        'topic: "Altman Z — Yahoo balance-sheet safety"',
        'tags: ["safety", "altman-z"]',
        "---",
        "",
        f"# Altman-Z Safety (Yahoo) — {today}",
        "",
        "| Ticker | Z | Zone |",
        "|--------|---|------|",
    ]
    ranked = sorted([d for d in data if not d.get("blank")],
                    key=lambda x: x.get("z") if x.get("z") is not None else -99,
                    reverse=True)
    for d in ranked:
        lines.append(f"| {d['ticker']} | {d['z']} | {d['zone']} |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | |")
    path = os.path.join(notes_dir, f"{today} Altman-Z.md")
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
    print(f"Altman-Z for {len(ranked)} of {len(tickers)} tickers; {len(blanks)} blank")
    for row in sorted(ranked, key=lambda r: r.get("z") or -99, reverse=True)[:10]:
        print(f"  {row['ticker']:6} Z {row['z']} ({row['zone']})")
    for row in blanks:
        print(f"  {row['ticker']:6} blank — no usable Yahoo statements")
    write_note(today, data, args.result_json)


if __name__ == "__main__":
    main()
