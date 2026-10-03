#!/usr/bin/env python3
"""growth_momentum.py — revenue growth and its direction, from Yahoo statements.

Yahoo-backed: per-ticker income statements come from Yahoo Finance via
``yahoo_client.YahooClient`` (the only allowed Yahoo path — never call
``yf.Ticker`` directly). The built-in ticker list (or ``--tickers``) is a
symbol-selection input only; every comparison is computed WITHIN each company.

Honesty constraints built in:
  * Fiscal year ends differ (MU Aug, NVDA Jan, TSM Dec, WDC Jun). YoY is computed WITHIN each company, so
    a comparison across names is directional, not calendar-aligned.
  * Growth rates are currency-neutral; absolute revenue is not.
  * Blank periods are skipped, never treated as zero.
  * The newest period can be partially populated, so a missing revenue figure ends the series rather than
    producing a fake -100%.
  * Tickers with no usable Yahoo statements are reported as blank, never fabricated.

Usage:
  python3 growth_momentum.py                   # curated universe
  python3 growth_momentum.py --tickers MU,NVDA  # subset
"""
import argparse
import csv
import json
import os
import tempfile

from demo_universe import GROWTH_TICKERS as DEFAULT_TICKERS

REVENUE_ROWS = ("total revenue", "total revenues", "revenue", "revenues", "sales",
                "total net sales", "net sales", "total operating revenue")


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        from yahoo_client import YahooClient
        return YahooClient()
    if hasattr(provider, "get_financials"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_financials, or a provider callable")


def _safe_financials(client, ticker, kind):
    """Yahoo statements for one ticker/kind; None when unavailable.

    Rate-limit RuntimeErrors propagate (fail fast); per-ticker gaps are blank.
    """
    try:
        frame = client.get_financials(ticker, kind)
    except RuntimeError:
        raise
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True):
        return None
    return frame


def revenue_series(frame, metric_names=REVENUE_ROWS):
    """Oldest -> newest (labels, values) revenue floats. Blanks skipped, never zero."""
    try:
        index = {str(label).strip().lower(): label for label in frame.index}
    except Exception:
        return [], []
    key = next((index[name] for name in metric_names if name in index), None)
    if key is None:
        return [], []
    try:
        row = frame.loc[key].sort_index()
        labels = [str(c) for c in row.index]
        raw = list(row.values)
    except Exception:
        return [], []
    cols, vals = [], []
    for label, value in zip(labels, raw):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number:  # NaN: blank, skip
            continue
        cols.append(label)
        vals.append(number)
    return cols, vals


def pct(x):
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def analyse_ticker(ticker, annual_frame, quarterly_frame):
    """Within-company YoY rows for one ticker: [(ticker, kind, last, prev, note)]."""
    out = []
    for kind, frame in (("annual", annual_frame), ("quarterly", quarterly_frame)):
        if frame is None:
            out.append((ticker, kind, None, None, "blank (no usable Yahoo statements)"))
            continue
        cols, vals = revenue_series(frame)
        if len(vals) < 2:
            out.append((ticker, kind, None, None,
                        "blank — insufficient periods (" + str(len(vals)) + ")"))
            continue
        if kind == "quarterly":
            growths = []
            for i in range(4, len(vals)):
                if vals[i - 4]:
                    growths.append(vals[i] / vals[i - 4] - 1)
        else:
            growths = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
        if not growths:
            out.append((ticker, kind, None, None, "blank — no comparable pair"))
            continue
        last = growths[-1]
        prev = growths[-2] if len(growths) > 1 else None
        trend = "n/a" if prev is None else ("ACCELERATING" if last > prev else "decelerating")
        out.append((ticker, kind, last, prev, trend + " (" + cols[-1] + ")"))
    return out


def screen_tickers(tickers, provider=None):
    """Within-company YoY analysis for each ticker. One or two rows per ticker."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        quarterly = _safe_financials(client, ticker, "quarterly-income")
        annual = _safe_financials(client, ticker, "income")
        rows.extend(analyse_ticker(ticker, annual, quarterly))
    return rows


def qoq_rows(tickers, provider=None):
    """Sequential (quarter-on-quarter) growth per ticker — the sharper rollover signal."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        frame = _safe_financials(client, ticker, "quarterly-income")
        if frame is None:
            rows.append((ticker, None, "blank (no usable Yahoo statements)"))
            continue
        _, vals = revenue_series(frame)
        if len(vals) < 3:
            rows.append((ticker, None, "blank — only " + str(len(vals)) + " periods"))
            continue
        growths = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
        if not growths:
            rows.append((ticker, None, "blank — no comparable pair"))
            continue
        trend = "n/a" if len(growths) < 2 else ("accelerating" if growths[-1] > growths[-2]
                                                else "decelerating")
        rows.append((ticker, growths[-1], trend + " (" + ", ".join(pct(g) for g in growths) + ")"))
    return rows


def payload_from_parts(rows, sequential_map, report_path=None):
    """Rank YoY rows with a sequential-QoQ map; blanks last with "blank" detail.

    Shared core behind :func:`build_rotation_payload`,
    :func:`build_result_payload`, and ``main()`` so every path carries the
    same blank-in-top contract and the same QoQ signal.
    """
    quarterly = [r for r in rows if r[1] == "quarterly" and isinstance(r[2], float)]
    blanks = sorted({r[0] for r in rows if not isinstance(r[2], float)})
    top = []
    for rank, (tk, kind, last, prev, note) in enumerate(
            sorted(quarterly, key=lambda r: -r[2])[:10], 1):
        seq = sequential_map.get(tk, (None, ""))[0]
        top.append({
            "rank": rank,
            "ticker": tk,
            "name": tk,
            "detail": (f"quarterly YoY {pct(last)} (prior {pct(prev)}, "
                       f"{note.split('(')[0].strip()}); sequential QoQ {pct(seq)}"),
        })
    for tk in blanks:
        if len(top) >= 10:
            break
        top.append({
            "rank": len(top) + 1,
            "ticker": tk,
            "name": tk,
            "detail": f"blank — insufficient Yahoo statements for {tk}; no growth signal",
        })
    return {
        "summary": (f"{len(quarterly)} quarterly YoY signals; "
                    f"{len(blanks)} blank (insufficient Yahoo statements)"),
        "report_path": str(report_path) if report_path else None,
        "top": top,
    }


def _sequential_map(rows, provider, sequential):
    """Resolve the ticker -> (qoq_last, note) map for a rows payload."""
    if sequential is not None:
        return sequential
    if provider is None:
        return {}
    tickers = sorted({r[0] for r in rows})
    return {tk: (last, note) for tk, last, note in qoq_rows(tickers, provider=provider)}


def build_rotation_payload(tickers, report_path=None, provider=None):
    """Ranked payload for the CLI dashboard, fetched via Yahoo.

    Missing data ranks last with a "blank" detail, never fabricated.
    """
    tickers = [t.strip().upper() for t in tickers if t.strip()]
    rows = screen_tickers(tickers, provider=provider)
    sequential = {tk: (last, note) for tk, last, note in qoq_rows(tickers, provider=provider)}
    return payload_from_parts(rows, sequential, report_path)


def build_result_payload(tickers_or_rows, report_path=None, provider=None, sequential=None):
    """Ranked payload for the CLI dashboard.

    Accepts either a list of ticker symbols (fetched via Yahoo, same as
    :func:`build_rotation_payload`) or a list of pre-screened
    (ticker, kind, last, prev, note) rows. For rows, pass ``sequential``
    (a ticker -> (qoq_last, note) map, e.g. from :func:`qoq_rows`) or a
    ``provider`` to recompute it; otherwise the sequential leg honestly
    reads n/a since no statements are available without a fetch.
    """
    if tickers_or_rows and all(isinstance(c, str) for c in tickers_or_rows):
        return build_rotation_payload(tickers_or_rows, report_path, provider=provider)
    rows = list(tickers_or_rows)
    return payload_from_parts(
        rows, _sequential_map(rows, provider, sequential), report_path)


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path) or ".",
            prefix=".growth-momentum-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers")
    ap.add_argument("--csv-out", default=os.path.join(os.getcwd(), "growth_momentum.csv"))
    ap.add_argument("--result-json", help="write the ranked shortlist for the CLI dashboard")
    a = ap.parse_args(argv)
    tickers = ([t.strip().upper() for t in a.tickers.split(",") if t.strip()]
               if a.tickers else list(DEFAULT_TICKERS))

    rows = screen_tickers(tickers)
    with open(a.csv_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "kind", "latest_yoy", "prior_yoy", "direction"])
        for tk, kind, last, prev, note in rows:
            w.writerow([tk, kind, last if last is not None else "",
                        prev if prev is not None else "", note])

    print("\n=== REVENUE YoY — WITHIN-COMPANY (Yahoo statements; cross-name is directional) ===")
    print(f"{'ticker':7} {'kind':10} {'latest YoY':>11} {'prior':>9}  {'direction':22} period")
    for tk, kind, last, prev, note in rows:
        period = note[note.find("("):] if "(" in note else ""
        print(f"{tk:7} {kind:10} {pct(last):>11} {pct(prev):>9}  "
              f"{note[:22]:22} {period}")

    q = [r for r in rows if r[1] == "quarterly" and isinstance(r[2], float)]
    print("\n=== QUARTERLY YoY (freshest signal) ===")
    for tk, kind, last, prev, note in sorted(q, key=lambda r: -r[2]):
        print(f"   {tk:6} {pct(last):>9}   (prior {pct(prev)}, {note.split('(')[0].strip()})")
    print("\n=== SEQUENTIAL (QoQ) — the sharper signal for rollover ===")
    seq_rows = qoq_rows(tickers)
    for tk, last, note in sorted(seq_rows,
                                 key=lambda r: (r[1] is None, -(r[1] or 0))):
        print(f"   {tk:6} latest QoQ {pct(last):>9}  {note}")
    blanks = sorted({r[0] for r in rows if not isinstance(r[2], float)})
    if blanks:
        print("\n=== BLANK (insufficient Yahoo statements — not ranked) ===")
        for tk in blanks:
            print(f"   {tk:6} blank — no usable Yahoo statements")
    print(f"\nrows: {len(rows)}   csv: {a.csv_out}")
    if a.result_json:
        write_result_json(a.result_json, payload_from_parts(
            rows, {tk: (last, note) for tk, last, note in seq_rows},
            os.path.abspath(a.csv_out)))


if __name__ == "__main__":
    main()
