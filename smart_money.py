#!/usr/bin/env python3
"""Rank institutional ownership from Yahoo Finance.

Yahoo-backed: holder tables come from Yahoo Finance via ``yahoo_client``
(the only allowed Yahoo path — never call ``yf.Ticker`` directly). The
ticker list is an explicit ``--tickers`` selection or the shared built-in
universe; nothing is read from local portfolio files.

Usage:
    python3 smart_money.py [--tickers VZ,JNJ] [--result-json out/smart-money.json]
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
    if hasattr(provider, "get_holders"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_holders, or a provider callable")


def _pct_of_float(frame):
    """Total institutional % of float from a holders frame; None when unusable."""
    try:
        columns = [str(c) for c in (frame.columns if frame is not None else [])]
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True):
        return None, 0
    key = next((c for c in columns
                if c.strip().lower() in ("% out", "%out", "pct", "percent", "%")), None)
    if key is None:
        return None, 0
    try:
        import pandas as pd

        series = pd.to_numeric(frame[key], errors="coerce").dropna()
    except Exception:
        return None, 0
    if series.empty:
        return None, 0
    total = float(series.sum())
    if total > 1:  # already in percent
        total = total / 100
    return total, len(series)


def screen_tickers(tickers, provider=None):
    """Institutional ownership rows for the given tickers, fetched via Yahoo only."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        try:
            frame = client.get_holders(ticker)
        except RuntimeError:
            raise
        except Exception:
            frame = None
        pct, count = _pct_of_float(frame)
        if pct is None:
            rows.append({"ticker": ticker, "blank": True})
            continue
        rows.append({"ticker": ticker, "pct": round(pct * 100, 1), "holders": count})
    return rows


def build_result_payload(data, report_path):
    measured = [r for r in data if not r.get("blank")]
    blanks = [r for r in data if r.get("blank")]
    ranked = sorted(measured, key=lambda row: row.get("pct") or 0, reverse=True)
    top = []
    for rank, row in enumerate(ranked, 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"Inst {row['pct']}% of float (n={row['holders']} holders)",
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no Yahoo holder info for {row['ticker']}",
        })
    return {
        "summary": (f"{len(ranked)} names with Yahoo holder info "
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
            prefix=".smart-money-", suffix=".tmp", delete=False,
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
        'topic: "Smart money — Yahoo institutional ownership"',
        'tags: ["ownership", "institutions"]',
        "---",
        "",
        f"# Smart Money (Yahoo) — {today}",
        "",
        "| Ticker | Inst % | Holders |",
        "|--------|--------|---------|",
    ]
    ranked = sorted([d for d in data if not d.get("blank")],
                    key=lambda x: x.get("pct") or 0, reverse=True)
    for d in ranked:
        lines.append(f"| {d['ticker']} | {d['pct']}% | {d['holders']} |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | |")
    path = os.path.join(notes_dir, f"{today} Smart-Money.md")
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
    print(f"Smart money for {len(ranked)} of {len(tickers)} tickers; {len(blanks)} blank")
    for row in sorted(ranked, key=lambda r: r.get("pct") or 0, reverse=True)[:10]:
        print(f"  {row['ticker']:6} inst {row['pct']}% (n={row['holders']})")
    for row in blanks:
        print(f"  {row['ticker']:6} blank — no Yahoo holder info")
    write_note(today, data, args.result_json)


if __name__ == "__main__":
    main()
