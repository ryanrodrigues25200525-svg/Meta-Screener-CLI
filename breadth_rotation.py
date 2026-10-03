#!/usr/bin/env python3
"""breadth_rotation.py — market breadth and rotation from Yahoo prices.

Yahoo-backed: per-ticker daily closes come from Yahoo Finance via
``yahoo_client`` (the only allowed Yahoo path — never call ``yf.Ticker``
directly). The symbol lists below (``DEFAULT_TICKERS``, ``BOOK``,
``SEMIS``, ``BENCH``) are symbol-selection inputs only; breadth is computed
from Yahoo closes. No local price files, no Knowledge Graph reads.

Breadth: share of names above their long moving average (200-day when
history allows, else 50-day) and share with a positive 3m return.
Rotation: 1m/3m returns aggregated by group membership.

Usage:
    python3 breadth_rotation.py [--tickers AAPL,MSFT] [--top N]
        [--result-json out/breadth.json]
"""

import argparse
import json
import os
import statistics
import tempfile

from demo_universe import ROTATION_TICKERS as DEFAULT_TICKERS

# Symbol-selection inputs only: membership implies nothing about breadth.
BOOK = {"GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE", "AAOI",
        "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL", "NVDA", "TSM",
        "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO"}
SEMIS = {"AAOI", "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL", "NVDA",
         "TSM", "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO", "ALAB", "CRDO",
         "COHR", "ACLS", "CAMT", "FORM", "SWKS", "TER", "NVMI", "DIOD", "AMAT", "INTC", "KLAC", "LRCX"}

BENCH = "SPY"

MIN_BARS = 30
TOP_N = 10


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_history"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_history, or a provider callable")


def _safe_history(client, ticker, period="6mo"):
    """Yahoo history frame for one ticker; None when unavailable.

    Rate-limit RuntimeErrors propagate (fail fast); per-ticker gaps are blank.
    """
    try:
        frame = client.get_history(ticker, period)
    except RuntimeError:
        raise
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True):
        return None
    return frame


def _closes_from_frame(frame):
    """Daily closes oldest -> newest as floats. Blanks skipped, never zero."""
    try:
        columns = list(getattr(frame, "columns", []) or [])
    except Exception:
        columns = []
    lowered = {str(c).strip().lower(): c for c in columns}
    key = next((lowered[name] for name in ("close", "adj close") if name in lowered), None)
    try:
        series = frame[key] if key is not None else frame.iloc[:, 0]
        values = list(series.values)
    except Exception:
        return []
    out = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number or number <= 0:  # NaN or non-positive: blank, skip
            continue
        out.append(number)
    return out


def ret(c, n):
    return (c[-1] / c[-1 - n] - 1) * 100 if len(c) > n and c[-1 - n] > 0 else None


def screen_tickers(tickers, provider=None, period="6mo"):
    """Breadth rows for each ticker from its own Yahoo history. One row per ticker."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        frame = _safe_history(client, ticker, period)
        closes = _closes_from_frame(frame) if frame is not None else []
        row = {"ticker": ticker}
        if len(closes) < MIN_BARS:
            row["note"] = "blank — no usable Yahoo history"
            rows.append(row)
            continue
        window = 200 if len(closes) >= 210 else (50 if len(closes) >= 60 else len(closes))
        ma = statistics.mean(closes[-window:])
        row["closes"] = len(closes)
        row["ma_window"] = window
        row["above"] = closes[-1] > ma
        row["ma_dist"] = (closes[-1] / ma - 1) * 100 if ma > 0 else None
        row["r1"] = ret(closes, 21)
        row["r3"] = ret(closes, 63)
        row["r6"] = ret(closes, 126)
        rows.append(row)
    return rows


def payload_from_rows(rows, report_path=None, top_n=TOP_N):
    """Rank breadth rows by distance above the long MA; blanks last with "blank" detail."""
    ranked = sorted(
        [r for r in rows if r.get("ma_dist") is not None],
        key=lambda item: -item["ma_dist"],
    )
    blanks = [r for r in rows if r.get("ma_dist") is None]
    measured = [r for r in rows if r.get("ma_dist") is not None]
    above = sum(1 for r in measured if r.get("above"))
    pos3 = sum(1 for r in measured if (r.get("r3") or 0) > 0)
    top = []
    for rank, row in enumerate(ranked[:top_n], 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (
                f"{row['ma_dist']:+.1f}% vs long MA ({row['ma_window']}d); "
                f"3m {row['r3']:+.1f}%" if row.get("r3") is not None
                else f"{row['ma_dist']:+.1f}% vs long MA ({row['ma_window']}d)"
            ),
        })
    for row in blanks:
        if len(top) >= top_n:
            break
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (f"blank — no usable Yahoo history for {row['ticker']}; "
                       "no breadth signal"),
        })
    return {
        "summary": (f"Market breadth across {len(measured)} names with Yahoo history: "
                    f"{above} above their long MA; {pos3} with a positive 3m return; "
                    f"{len(blanks)} blank (no usable Yahoo history)"),
        "report_path": str(report_path) if report_path else None,
        "top": top,
    }


def compute_breadth(tickers, provider=None, period="6mo", report_path=None, top_n=TOP_N):
    """Market-breadth payload for the given tickers, fetched via Yahoo.

    Tickers without usable Yahoo history rank last with a "blank" detail,
    never fabricated.
    """
    return payload_from_rows(
        screen_tickers(tickers, provider=provider, period=period),
        report_path, top_n,
    )


def build_breadth_payload(tickers, report_path=None, provider=None,
                          period="6mo", top_n=TOP_N):
    """Ranked payload for the CLI dashboard (same contract as compute_breadth)."""
    return compute_breadth(tickers, provider=provider, period=period,
                           report_path=report_path, top_n=top_n)


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path) or ".",
            prefix=".breadth-rotation-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def stats(rows, label):
    subset = [r for r in rows if r.get("ma_dist") is not None]
    if not subset:
        print("   %s: no data" % label)
        return
    above = sum(1 for r in subset if r["above"])
    pos3 = sum(1 for r in subset if (r["r3"] or 0) > 0)
    med3 = statistics.median([r["r3"] for r in subset if r["r3"] is not None])
    med1 = statistics.median([r["r1"] for r in subset if r["r1"] is not None])
    print("   %-22s n=%4d  above long MA %3.0f%%   positive 3m %3.0f%%   median 1m %+5.1f%%   median 3m %+6.1f%%"
          % (label, len(subset), 100.0 * above / len(subset), 100.0 * pos3 / len(subset), med1, med3))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers",
                    help="comma-separated symbols; default: built-in selection list")
    ap.add_argument("--top", type=int, default=TOP_N)
    ap.add_argument("--result-json", help="write the ranked breadth for the CLI dashboard")
    a = ap.parse_args(argv)
    tickers = ([t.strip().upper() for t in a.tickers.split(",") if t.strip()]
               if a.tickers else list(DEFAULT_TICKERS))

    rows = screen_tickers(tickers)
    print("=== breadth (Yahoo daily closes) ===")
    stats(rows, "whole universe")
    stats([r for r in rows if r["ticker"] in BOOK], "the book")
    stats([r for r in rows if r["ticker"] in SEMIS], "semis / AI complex")
    stats([r for r in rows if r["ticker"] in BOOK and r["ticker"] not in SEMIS], "book ex-semis")

    payload = payload_from_rows(rows, top_n=a.top)
    print("\n%s" % payload["summary"])
    for row in payload["top"]:
        print("   %2d. %-6s %s" % (row["rank"], row["ticker"], row["detail"]))
    if a.result_json:
        write_result_json(a.result_json, payload_from_rows(rows, os.path.abspath(a.result_json), a.top))


if __name__ == "__main__":
    main()
