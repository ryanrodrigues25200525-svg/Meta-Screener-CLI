#!/usr/bin/env python3
"""Fetch short interest data from Yahoo Finance.

Yahoo-backed: short-interest fields come from Yahoo Finance ``info`` via
``yahoo_client`` (the only allowed Yahoo path — never call ``yf.Ticker``
directly). The ticker list is an explicit ``--tickers`` selection or the
shared built-in universe; nothing is read from local portfolio files.

Usage:
    python3 short_interest.py [--tickers TICKER1,TICKER2]
        [--result-json out/short-interest.json]
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


def fetch_short_interest(tickers, provider=None):
    """Yahoo short-interest rows for each ticker. One row per ticker."""
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
            si_pct = info.get("shortPercentOfFloat", 0) or 0
            si_ratio = info.get("shortRatio", 0) or 0
            shares_short = info.get("sharesShort", 0) or 0
        except AttributeError:
            results.append({"ticker": ticker, "blank": True})
            continue
        results.append({
            "ticker": ticker,
            "short_pct": round(si_pct * 100, 2) if si_pct else 0,
            "short_ratio": round(si_ratio, 2) if si_ratio else 0,
            "shares_short": shares_short,
            "flag": "HIGH" if si_pct and si_pct > 0.20 else "ELEVATED" if si_pct and si_pct > 0.10 else "NORMAL",
        })
    return results


def screen_tickers(tickers, provider=None):
    """Short-interest rows for the given tickers, fetched via Yahoo only."""
    return fetch_short_interest(tickers, provider=provider)


def build_result_payload(data, report_path, top_n=10):
    ranked = sorted(
        [r for r in data if not r.get("blank")],
        key=lambda row: row.get("short_pct") or 0, reverse=True,
    )[:top_n]
    blanks = [r for r in data if r.get("blank")]
    top = []
    for rank, row in enumerate(ranked, 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (
                f"Short {row.get('short_pct') or 0}% of float; "
                f"{row.get('short_ratio') or 0} days to cover; {row.get('flag', 'UNKNOWN')}"
            ),
        })
    for row in blanks:
        if len(top) >= top_n:
            break
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no Yahoo short-interest info for {row['ticker']}",
        })
    return {
        "summary": (f"{len(ranked)} names with Yahoo short interest "
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
            prefix=".short-interest-", suffix=".tmp", delete=False,
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
        'topic: "Short interest scan — Yahoo short-interest fields"',
        'tags: ["short-interest", "sentiment"]',
        "---",
        "",
        f"# Short Interest Scan (Yahoo) — {today}",
        "",
        "| Ticker | Short % Float | Days to Cover | Shares Short | Flag |",
        "|--------|---------------|---------------|--------------|------|",
    ]
    ranked = sorted([d for d in data if not d.get("blank")],
                    key=lambda x: x.get("short_pct") or 0, reverse=True)
    for d in ranked:
        shares = f'{d["shares_short"]:,}' if d.get("shares_short") else "N/A"
        lines.append(f"| {d['ticker']} | {d.get('short_pct', 0)}% | {d.get('short_ratio', 0)} | {shares} | {d.get('flag', 'n/a')} |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | | | |")
    flagged = [d["ticker"] for d in ranked if d.get("flag") in ("HIGH", "ELEVATED")]
    if flagged:
        lines.extend(["", f"**Flagged:** {', '.join(flagged)}"])
    path = os.path.join(notes_dir, f"{today} Short-Interest.md")
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
    if not tickers:
        print("No tickers found. Use --tickers")
        return
    data = fetch_short_interest(tickers)
    write_note(today, data, args.result_json)
    print(f"Scanned {len(data)} tickers")


if __name__ == "__main__":
    main()
