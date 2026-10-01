#!/usr/bin/env python3
"""stop_regime_test.py — does the 15% trailing stop pay in a DRAWDOWN regime?

The 2025-2026 measurement showed the stop cutting winners, but that window was a violent uptrend and a
trailing stop is meant to earn its keep in a break. This runs the same rule over 2022 (semis drawdown) and
compares: for each name, what a 15% trailing stop that exits and stays in cash would have saved or cost
versus buy-and-hold.
"""
import csv, os, statistics

D = "/documents/Finance Knowledge Graph/Datasets/History/prices_daily"
NAMES = ["AAOI", "AXTI", "MU", "LITE", "MTSI", "SIMO", "ONTO", "RMBS", "TSEM", "AEIS", "NVDA", "TSM",
         "AVGO", "AMD", "MRVL", "WDC", "GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO",
         "PBR", "PFE", "ADBE", "SPY"]
STOP = 0.15
PERIODS = {"2022 drawdown": ("2022-01-01", "2022-12-31"),
           "2025-26 uptrend": ("2025-02-14", "2026-09-15")}


def load(tk):
    p = os.path.join(D, tk + ".csv")
    if not os.path.exists(p):
        return []
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
        try:
            out.append((r["date"][:10], float(r["close"])))
        except (ValueError, KeyError):
            pass
    return out


for label, (start, end) in PERIODS.items():
    rows = []
    skipped = []
    for tk in NAMES:
        s = [x for x in load(tk) if start <= x[0] <= end]
        if len(s) < 60:
            # Observed failure mode: this returned nothing and the whole period printed as EMPTY, which is
            # how the daily layer's 2018-2022 hole was discovered. Say so instead of skipping silently.
            skipped.append((tk, len(s)))
            continue
        peak = s[0][1]
        exit_px = None
        for d, px in s:
            if px > peak:
                peak = px
            if exit_px is None and px / peak - 1 <= -STOP:
                exit_px = px
        bh = s[-1][1] / s[0][1] - 1
        # stop strategy: hold until the trigger (sell there), then cash for the rest of the period
        st = (exit_px / s[0][1] - 1) if exit_px is not None else bh
        rows.append((tk, bh, st, st - bh, exit_px is not None))
    if not rows:
        print("\n=== %s (%s to %s) ===" % (label, start, end))
        print("   NO DATA for this period in %d of %d series - do not read this as 'no effect'."
              % (len(skipped), len(NAMES)))
        print("   first few: " + ", ".join("%s(%d bars)" % (t, n) for t, n in skipped[:6]))
        continue
    if skipped:
        print("\n   NOTE: %d series skipped for insufficient bars in this period" % len(skipped))
    saved = [r[3] for r in rows if r[4]]
    print("\n=== %s (%s to %s) ===" % (label, start, end))
    print("%-6s %10s %10s %10s" % ("name", "buy&hold", "with stop", "difference"))
    for tk, bh, st, diff, trig in sorted(rows, key=lambda r: r[3]):
        flag = "" if trig else "   (no trigger)"
        print("%-6s %9.1f%% %9.1f%% %+9.1f%%%s" % (tk, bh * 100, st * 100, diff * 100, flag))
    if saved:
        print("names triggered: %d of %d | median difference %+.1f%% | stop HELPED on %d, hurt on %d"
              % (len(saved), len(rows), statistics.median(saved) * 100,
                 sum(1 for x in saved if x > 0), sum(1 for x in saved if x < 0)))
