#!/usr/bin/env python3
"""Check unusual options activity from Yahoo Finance.

Yahoo-backed: expirations and chains come from Yahoo Finance via
``yahoo_client`` (the only allowed Yahoo path — never call ``yf.Ticker``
directly). The ticker list is an explicit ``--tickers`` selection or the
shared built-in universe; nothing is read from local portfolio files.

Usage:
    python3 unusual_options.py [--tickers TICKER1,TICKER2]
        [--result-json out/options.json]
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
    if hasattr(provider, "get_options") and hasattr(provider, "get_option_chain"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_options/get_option_chain, or a provider callable")


def _chain_frames(chain):
    """Option-chain result (dict or yfinance tuple) -> (calls, puts) frames."""
    if chain is None:
        return None, None
    if isinstance(chain, dict):
        return chain.get("calls"), chain.get("puts")
    calls = getattr(chain, "calls", None)
    puts = getattr(chain, "puts", None)
    if calls is None and puts is None:
        return None, None
    return calls, puts


def _frame_sums(frame):
    """(total volume, total open interest) for one side; None when unusable."""
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        volume = frame["volume"].sum() if "volume" in frame.columns else None
        interest = frame["openInterest"].sum() if "openInterest" in frame.columns else None
        unusual = frame[frame["volume"] > frame["openInterest"] * 2] if (
            "volume" in frame.columns and "openInterest" in frame.columns
        ) else []
    except Exception:
        return None
    try:
        return int(volume or 0), int(interest or 0), int(len(unusual))
    except (TypeError, ValueError):
        return None


def check_options(ticker, client=None):
    """Yahoo options summary for one ticker, or None when unavailable.

    Rate-limit RuntimeErrors propagate (fail fast); per-ticker gaps are blank.
    """
    holder = client if client is not None else _client_for(None)
    try:
        expirations = holder.get_options(ticker)
    except RuntimeError:
        raise
    except Exception:
        return None
    if not expirations:
        return None
    expiry = expirations[0]
    try:
        chain = holder.get_option_chain(ticker, expiry)
    except RuntimeError:
        raise
    except Exception:
        return None
    calls, puts = _chain_frames(chain)
    call_stats = _frame_sums(calls)
    put_stats = _frame_sums(puts)
    if call_stats is None and put_stats is None:
        return None
    call_vol, _call_oi, unusual_calls = call_stats or (0, 0, 0)
    put_vol, _put_oi, unusual_puts = put_stats or (0, 0, 0)
    pc_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else 0
    return {
        "ticker": ticker,
        "expiry": str(expiry),
        "call_vol": call_vol,
        "put_vol": put_vol,
        "pc_ratio": pc_ratio,
        "unusual_calls": unusual_calls,
        "unusual_puts": unusual_puts,
        "flag": "UNUSUAL" if unusual_calls > 0 or unusual_puts > 0 else "NORMAL",
    }


def screen_tickers(tickers, provider=None):
    """Yahoo options rows for each ticker. One row per ticker with a chain."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        result = check_options(ticker, client=client)
        if result is None:
            rows.append({"ticker": ticker, "blank": True})
        else:
            rows.append(result)
    return rows


def build_result_payload(data, report_path):
    measured = [r for r in data if not r.get("blank")]
    blanks = [r for r in data if r.get("blank")]
    unusual = [r for r in measured if r.get("flag") == "UNUSUAL"]
    normal = [r for r in measured if r.get("flag") != "UNUSUAL"]
    top = []
    for rank, row in enumerate([*unusual, *normal], 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (
                f"Expiry {row.get('expiry', 'n/a')}; call vol {row.get('call_vol', 0):,}, "
                f"put vol {row.get('put_vol', 0):,}; P/C {row.get('pc_ratio', 0)}; "
                f"{row.get('unusual_calls', 0)} unusual calls, "
                f"{row.get('unusual_puts', 0)} unusual puts; {row.get('flag', 'n/a')}"
            ),
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no Yahoo options chain for {row['ticker']}",
        })
    return {
        "summary": (f"{len(unusual)} names with unusual Yahoo options activity "
                    f"out of {len(measured)} with chains; {len(blanks)} blank"),
        "report_path": str(report_path),
        "top": top,
    }


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path),
            prefix=".unusual-options-", suffix=".tmp", delete=False,
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
        'topic: "Unusual options activity scan — Yahoo chains"',
        'tags: ["options", "sentiment"]',
        "---",
        "",
        f"# Unusual Options Activity (Yahoo) — {today}",
        "",
        "| Ticker | Expiry | Call Vol | Put Vol | P/C Ratio | Unusual Calls | Unusual Puts | Flag |",
        "|--------|--------|----------|---------|-----------|---------------|--------------|------|",
    ]
    for d in [d for d in data if not d.get("blank")]:
        lines.append(f"| {d['ticker']} | {d.get('expiry', '')} | {d.get('call_vol', 0):,} | {d.get('put_vol', 0):,} | {d.get('pc_ratio', 0)} | {d.get('unusual_calls', 0)} | {d.get('unusual_puts', 0)} | {d.get('flag', '')} |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | | | | | | |")
    flagged = [d["ticker"] for d in data if d.get("flag") == "UNUSUAL"]
    if flagged:
        lines.extend(["", f"**Unusual activity:** {', '.join(flagged)}"])
    path = os.path.join(notes_dir, f"{today} Unusual-Options.md")
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
    ap.add_argument("--result-json", help="write the rows for the CLI dashboard")
    args = ap.parse_args(argv)
    today = date.today().isoformat()
    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
               if args.tickers else default_tickers())
    if not tickers:
        print("No tickers found. Use --tickers")
        return
    rows = screen_tickers(tickers)
    measured = [r for r in rows if not r.get("blank")]
    write_note(today, rows, args.result_json)
    print(f"Scanned {len(measured)} tickers with chains ({len(rows)} requested)")


if __name__ == "__main__":
    main()
