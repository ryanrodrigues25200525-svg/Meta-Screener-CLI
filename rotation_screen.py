#!/usr/bin/env python3
"""rotation_screen.py — rank a curated book on revenue growth, margin trend and valuation.

Yahoo-backed: per-ticker income statements and info come from Yahoo Finance via
``yahoo_client.YahooClient`` (the only allowed Yahoo path — never call
``yf.Ticker`` directly). The built-in ticker list (or ``--tickers``) is a
symbol-selection input only; every comparison is computed WITHIN each company.

Honesty constraints (same spirit as growth_momentum.py):
  * Sequential (QoQ) growth is computed WITHIN each company; fiscal quarter ends differ, so cross-name
    comparison is directional, not calendar-aligned.
  * Blank periods are skipped, never treated as zero, and a blank revenue ends the run rather than
    producing a fake -100%.
  * Valuation needs ONE currency. Where the info currency differs from USD the
    row is marked and P/S is left blank unless an FX rate is supplied on the command line
    (--fx DKK=0.1570 converts into USD). A wrong-currency ratio is worse than a blank.
  * P/E is blank for loss-makers or when TTM net income <= 0. Never a negative multiple.
  * Tickers with no usable Yahoo statements are ranked last with a "blank" detail, never fabricated.

Usage:
  python3 rotation_screen.py                      # curated universe
  python3 rotation_screen.py --tickers MU,NVDA    # subset
  python3 rotation_screen.py --fx DKK=0.1570
"""
import argparse
import csv
import json
import os
import statistics
import sys
import tempfile

# Curated universe: symbol-selection input only. No KG reads; membership here
# implies nothing about a company's fundamentals.
DEFAULT_TICKERS = """
AAPL MSFT NVDA AMZN GOOGL META AVGO AMD MU TSM
VTRS HPQ GM VALE PFE NVO ADBE PBR JPM XOM
""".split()

BOOK = ["VTRS", "HPQ", "GM", "VALE", "SM", "PFE", "PRU", "NVO", "ADBE", "CAG", "GIS", "PBR"]

# yfinance-style statement row names, matched case-insensitively.
REVENUE_ROWS = ("total revenue", "total revenues", "revenue", "revenues", "sales",
                "total net sales", "net sales", "total operating revenue")
GROSS_PROFIT_ROWS = ("gross profit", "gross income")
OPERATING_INCOME_ROWS = ("operating income", "operating income loss", "ebit")
NET_INCOME_ROWS = ("net income", "net earnings", "net income loss",
                   "net income applicable to common shares")


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        from yahoo_client import YahooClient
        return YahooClient()
    if hasattr(provider, "get_financials") and hasattr(provider, "get_info"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_financials/get_info, or a provider callable")


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


def _safe_info(client, ticker):
    try:
        info = client.get_info(ticker)
    except RuntimeError:
        raise
    except Exception:
        return {}
    return info if isinstance(info, dict) else {}


def _row_series(frame, row_names):
    """Oldest -> newest (label, value) floats for the first matching row.

    Blanks are skipped, never treated as zero.
    """
    try:
        index = {str(label).strip().lower(): label for label in frame.index}
    except Exception:
        return []
    key = next((index[name] for name in row_names if name in index), None)
    if key is None:
        return []
    try:
        row = frame.loc[key].sort_index()
        labels = list(row.index)
        values = list(row.values)
    except Exception:
        return []
    out = []
    for label, value in zip(labels, values):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number:  # NaN: blank, skip
            continue
        out.append((str(label), number))
    return out


def pct(x):
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def screen_tickers(tickers, provider=None, fx=None):
    """Screen tickers against their own Yahoo statements. One row per ticker."""
    fx = {k.upper(): v for k, v in (fx or {}).items()}
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        fq = _safe_financials(client, ticker, "quarterly-income")
        info = _safe_info(client, ticker)
        row = {"ticker": ticker,
               "group": "book" if ticker in BOOK else "other",
               "themes": ""}
        if fq is None:
            row["note"] = "blank — no usable Yahoo quarterly statements"
            rows.append(row)
            continue
        cur = (info.get("financialCurrency") or info.get("currency") or "?")
        row["currency"] = cur
        row["name"] = info.get("shortName") or info.get("longName") or ticker
        mcap = info.get("marketCap")
        try:
            row["mcap"] = float(mcap) if mcap else None
        except (TypeError, ValueError):
            row["mcap"] = None
        rev = _row_series(fq, REVENUE_ROWS)
        gp = dict(_row_series(fq, GROSS_PROFIT_ROWS))
        oi = dict(_row_series(fq, OPERATING_INCOME_ROWS))
        ni = _row_series(fq, NET_INCOME_ROWS)
        row["periods"] = len(rev)
        if len(rev) >= 2:
            vals = [v for _, v in rev]
            # A quarter that is <50% of BOTH neighbours is the signature of a partial period in the
            # provider's series. Left unflagged it reads as a real collapse and recovery.
            stubs = [rev[i][0] for i in range(1, len(vals) - 1)
                     if vals[i] and vals[i - 1] and vals[i + 1]
                     and vals[i] < 0.5 * min(vals[i - 1], vals[i + 1])]
            if stubs:
                row["suspect_partial_q"] = ",".join(stubs)
            qoq = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
            row["qoq_run"] = ", ".join(pct(x) for x in qoq)
            row["qoq_last"] = qoq[-1] if qoq else None
            row["qoq_prev"] = qoq[-2] if len(qoq) > 1 else None
            row["revenue_last"] = vals[-1]
            row["revenue_ttm"] = sum(vals[-4:]) if len(vals) >= 4 else None
            row["qoq_trend"] = ("accel" if (len(qoq) > 1 and qoq[-1] > qoq[-2]) else
                                ("decel" if len(qoq) > 1 else "n/a"))
            for name, src in (("gm", gp), ("om", oi)):
                s = [(c, src[c] / v) for (c, v) in rev if c in src and v]
                if len(s) >= 2:
                    row[name + "_last"] = s[-1][1]
                    row[name + "_prev"] = s[-2][1]
                    row[name + "_d4q"] = (s[-1][1] - s[-5][1]) if len(s) >= 5 else None
                    row[name + "_d1q"] = s[-1][1] - s[-2][1]
        nis = [v for _, v in ni]
        row["ni_ttm"] = sum(nis[-4:]) if len(nis) >= 4 else None
        if row.get("mcap") and row.get("revenue_ttm"):
            conv = 1.0
            if cur != "USD":
                conv = fx.get(str(cur).upper())
                row["fx_missing"] = conv is None
            if conv:
                row["ps_ttm"] = row["mcap"] / (row["revenue_ttm"] * conv)
        if row.get("mcap") and row.get("ni_ttm") and row["ni_ttm"] > 0:
            conv = 1.0 if cur == "USD" else fx.get(str(cur).upper())
            if conv:
                row["pe_ttm"] = row["mcap"] / (row["ni_ttm"] * conv)
        rows.append(row)
    return rows


def shortlist(rows):
    """Revenue accelerating sequentially, operating margin not deteriorating, valuation not rich.

    The valuation leg must be PRESENT to pass: an unknown P/S is not evidence of cheapness.
    Returns (candidates, unvalued).
    """
    cand, unvalued = [], []
    ps_all = [x["ps_ttm"] for x in rows if x.get("ps_ttm")]
    med = statistics.median(ps_all) if ps_all else None
    for r in rows:
        if r.get("qoq_trend") != "accel" or r.get("qoq_last") is None or r["qoq_last"] <= 0:
            continue
        if r.get("om_d4q") is not None and r["om_d4q"] < 0:
            continue
        if not r.get("ps_ttm"):
            unvalued.append(r)
            continue
        if med and r["ps_ttm"] > med:
            continue
        cand.append(r)
    return cand, unvalued


def build_rotation_payload(tickers, report_path=None, provider=None, fx=None):
    """Ranked payload for the CLI dashboard, fetched via Yahoo.

    Tickers without usable Yahoo statements rank last with a "blank"
    detail, never fabricated.
    """
    rows = screen_tickers(tickers, provider=provider, fx=fx)
    passing, _ = shortlist(rows)
    ranked = sorted(passing, key=lambda item: -item["qoq_last"])
    blanks = [r for r in rows if r.get("qoq_last") is None]
    top = []
    for rank, row in enumerate(ranked[:10], 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row.get("name") or row["ticker"],
            "detail": (
                f"QoQ revenue {pct(row['qoq_last'])}; "
                f"operating margin {(row.get('om_last') or 0) * 100:.1f}%; "
                f"P/S {row['ps_ttm']:.2f}x"
            ),
        })
    for row in blanks:
        if len(top) >= 10:
            break
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row.get("name") or row["ticker"],
            "detail": (f"blank — insufficient Yahoo statements for {row['ticker']}; "
                       "no growth, margin, or valuation signal"),
        })
    return {
        "summary": (f"{len(ranked)} companies passed the growth, margin, and valuation screen; "
                    f"{len(blanks)} blank (insufficient Yahoo statements)"),
        "report_path": str(report_path) if report_path else None,
        "top": top,
    }


def build_result_payload(candidates, csv_path=None, provider=None, fx=None):
    """Ranked payload for the CLI dashboard.

    Accepts either a list of ticker symbols (fetched via Yahoo, same as
    :func:`build_rotation_payload`) or a list of pre-screened row dicts
    (legacy ranked path).
    """
    if candidates and all(isinstance(c, str) for c in candidates):
        return build_rotation_payload(candidates, csv_path, provider=provider, fx=fx)
    top = []
    for rank, row in enumerate(sorted(candidates, key=lambda item: -item["qoq_last"])[:10], 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row.get("name") or row["ticker"],
            "detail": (
                f"QoQ revenue {pct(row['qoq_last'])}; "
                f"operating margin {row.get('om_last', 0) * 100:.1f}%; "
                f"P/S {row['ps_ttm']:.2f}x"
            ),
        })
    return {
        "summary": f"{len(top)} companies passed the growth, margin, and valuation screen",
        "report_path": str(csv_path),
        "top": top,
    }


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path) or ".",
            prefix=".rotation-screen-", suffix=".tmp", delete=False,
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
    ap.add_argument("--fx", action="append", default=[], help="CUR=rate_in_usd, e.g. DKK=0.1570")
    ap.add_argument("--csv-out", default=os.path.join(os.getcwd(), "rotation_screen.csv"))
    ap.add_argument("--result-json", help="write the ranked shortlist for the CLI dashboard")
    a = ap.parse_args(argv)
    fx = {}
    for item in a.fx:
        k, v = item.split("=")
        fx[k.upper()] = float(v)

    if a.tickers:
        tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    else:
        tickers = list(DEFAULT_TICKERS)
    rows = screen_tickers(tickers, fx=fx)

    keys = ["ticker", "name", "group", "currency", "periods", "qoq_last", "qoq_prev", "qoq_trend",
            "qoq_run", "revenue_last", "revenue_ttm", "ni_ttm", "mcap", "ps_ttm", "pe_ttm",
            "gm_last", "gm_d4q", "om_last", "om_d4q", "suspect_partial_q", "themes", "fx_missing"]
    with open(a.csv_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    def show(title, key, fmt, n=25):
        print("\n=== " + title + " ===")
        for r in sorted([x for x in rows if x.get(key) is not None], key=lambda x: -x[key])[:n]:
            print(f"   {r['ticker']:6} {fmt(r):>34}   {r['group']:8}")

    show("QoQ revenue growth — latest quarter (Yahoo statements, within-company)",
         "qoq_last", lambda r: f"{pct(r['qoq_last'])}  (run {r.get('qoq_run', 'n/a')})")
    show("Valuation — P/S on TTM revenue (lower = cheaper)", "ps_ttm", lambda r: f"{r['ps_ttm']:.2f}x")
    show("Valuation — P/E on TTM net income", "pe_ttm", lambda r: f"{r['pe_ttm']:.1f}x")

    print("\n=== gross-margin change over 4 quarters (bps) — expanding first ===")
    for r in sorted([x for x in rows if x.get("gm_d4q") is not None], key=lambda x: -x["gm_d4q"])[:25]:
        print(f"   {r['ticker']:6} {r['gm_d4q'] * 10000:+8.0f} bps   latest {r['gm_last'] * 100:5.1f}%   "
              f"{r['group']:8} latestQoQ {pct(r.get('qoq_last'))}")

    print("\n=== operating-margin change over 4 quarters (bps) — expanding first ===")
    for r in sorted([x for x in rows if x.get("om_d4q") is not None], key=lambda x: -x["om_d4q"])[:25]:
        print(f"   {r['ticker']:6} {r['om_d4q'] * 10000:+8.0f} bps   latest {r['om_last'] * 100:5.1f}%   "
              f"{r['group']:8} latestQoQ {pct(r.get('qoq_last'))}")

    print(f"\n=== series carrying a suspected PARTIAL quarter (a quarter < 50% of both neighbours — the QoQ "
          f"run through it is not a real move) ===")
    fl = [x for x in rows if x.get("suspect_partial_q")]
    for r in sorted(fl, key=lambda x: x["ticker"]):
        print(f"   {r['ticker']:6} partial: {r['suspect_partial_q']}   run {r.get('qoq_run')}")
    if not fl:
        print("   none")

    cand, unvalued = shortlist(rows)
    ps_all = [x["ps_ttm"] for x in rows if x.get("ps_ttm")]
    med = statistics.median(ps_all) if ps_all else None
    print(f"\n=== SHORTLIST (accel QoQ revenue + operating margin not deteriorating + P/S <= cohort median "
          f"{'' if med is None else format(med, '.2f') + 'x'}) ===")
    for r in sorted(cand, key=lambda x: -x["qoq_last"])[:20]:
        print(f"   {r['ticker']:6} QoQ {pct(r['qoq_last'])} (prior {pct(r.get('qoq_prev'))})  "
              f"om {(r.get('om_last') or 0) * 100:.1f}% (4q {(r.get('om_d4q') or 0) * 10000:+.0f}bps)  "
              f"P/S {'' if not r.get('ps_ttm') else format(r['ps_ttm'], '.2f') + 'x'}  {r['group']}")
    if not cand:
        print("   none — no name passed all three filters (see the note for why)")
    print(f"\n=== passes growth + margin, VALUATION NOT ESTABLISHED (P/S unavailable — not counted as passing) "
          f"===")
    for r in sorted(unvalued, key=lambda x: -x["qoq_last"]):
        print(f"   {r['ticker']:6} QoQ {pct(r['qoq_last'])}  om {(r.get('om_last') or 0) * 100:.1f}%  "
              f"currency {r['currency']}  {r['group']}")
    if not unvalued:
        print("   none")
    blanks = [x for x in rows if x.get("qoq_last") is None]
    if blanks:
        print(f"\n=== BLANK (insufficient Yahoo statements — not ranked, not counted as passing) ===")
        for r in sorted(blanks, key=lambda x: x["ticker"]):
            print(f"   {r['ticker']:6} blank — {r.get('note', 'no usable Yahoo statements')}")
    print(f"\nrows: {len(rows)}   csv: {a.csv_out}")
    if a.result_json:
        write_result_json(a.result_json, build_result_payload(cand, os.path.abspath(a.csv_out)))


if __name__ == "__main__":
    main()
