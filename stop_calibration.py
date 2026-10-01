#!/usr/bin/env python3
"""stop_calibration.py — how often would a 15% trailing stop have fired, on the book's own daily data?

The book runs 15% trailing stops. For names with 100%+ annualised vol (AXTI 138%, AAOI 140%), a 15% move
from peak can be ordinary noise, so the question is whether the stop sits inside the noise or outside it.
Counts distinct trigger episodes and the time spent stopped-out, per name.
"""
import csv, glob, os, statistics

D = "/documents/Finance Knowledge Graph/Datasets/History/prices_daily"
NAMES = ["AAOI", "AXTI", "POET", "AEHR", "NBIS", "MXL", "SNDK", "LITE", "MRVL", "SMTC", "MU", "RMBS",
         "SIMO", "ONTO", "TSEM", "WDC", "AMD", "AEIS", "MTSI", "NVDA", "TSM", "AVGO",
         "GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE"]
STOP = 0.15

print("%-6s %6s %8s %9s %9s %8s" % ("name", "bars", "episodes", "days>15%", "%of days", "ep/yr"))
print("-" * 54)
tot = {}
for tk in NAMES:
    p = os.path.join(D, tk + ".csv")
    if not os.path.exists(p):
        continue
    closes = []
    for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
        try:
            closes.append(float(r["close"]))
        except (ValueError, KeyError):
            pass
    if len(closes) < 200:
        continue
    # a 15% trailing stop: measured from the running peak, reset on each new peak
    peak = closes[0]
    episodes = 0
    armed = True
    days_below = 0
    for c in closes:
        if c > peak:
            peak = c
            if not armed:      # re-armed only after a new high, as a trailing stop would
                armed = True
        dd = c / peak - 1
        if dd <= -STOP:
            if armed:
                episodes += 1
                armed = False
        if dd <= -STOP:
            days_below += 1
    yrs = len(closes) / 252.0
    tot[tk] = (len(closes), episodes, days_below, 100.0 * days_below / len(closes), episodes / yrs)
    print("%-6s %6d %8d %9d %8.1f%% %8.1f" % (tk, len(closes), episodes, days_below,
                                               100.0 * days_below / len(closes), episodes / yrs))

ep = [v[4] for v in tot.values()]
print("-" * 54)
print("median trigger episodes per year across the book: %.1f" % statistics.median(ep))
print("names triggering more than 4x/yr: %d of %d" % (sum(1 for x in ep if x > 4), len(ep)))
