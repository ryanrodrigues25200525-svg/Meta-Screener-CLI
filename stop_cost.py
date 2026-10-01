#!/usr/bin/env python3
"""stop_cost.py — what happened AFTER each 15% trailing-stop trigger? Did the stop cut winners?

If a name triggered a 15% trailing stop and then beat SPY over the following 3 and 6 months, the stop cost
money in this book. Measured on the stored daily layer, with SPY as the benchmark.
"""
import csv, os, statistics

D = "/documents/Finance Knowledge Graph/Datasets/History/prices_daily"
NAMES = ["AAOI", "AXTI", "POET", "AEHR", "NBIS", "MXL", "SNDK", "LITE", "MRVL", "SMTC", "MU", "RMBS",
         "SIMO", "ONTO", "TSEM", "WDC", "AMD", "AEIS", "MTSI", "NVDA", "TSM", "AVGO",
         "GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE"]
STOP = 0.15


def load(tk):
    p = os.path.join(D, tk + ".csv")
    if not os.path.exists(p):
        return [], []
    d, c = [], []
    for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
        try:
            c.append(float(r["close"]))
            d.append(r["date"][:10])
        except (ValueError, KeyError):
            pass
    return d, c


sd, sc = load("SPY")
spy = dict(zip(sd, sc))


def forward(series_dates, series_closes, idx, days):
    j = idx + days
    if j >= len(series_closes) or series_closes[idx] <= 0:
        return None
    d0, d1 = series_dates[idx], series_dates[j]
    if d0 not in spy or d1 not in spy:
        return None
    return (series_closes[j] / series_closes[idx] - 1) - (spy[d1] / spy[d0] - 1)


res3, res6, per = [], [], {}
for tk in NAMES:
    d, c = load(tk)
    if len(c) < 200:
        continue
    peak, armed, trigs = c[0], True, []
    for i, px in enumerate(c):
        if px > peak:
            peak = px
            armed = True
        if armed and px / peak - 1 <= -STOP:
            trigs.append(i)
            armed = False
    f3 = [x for x in (forward(d, c, i, 63) for i in trigs) if x is not None]
    f6 = [x for x in (forward(d, c, i, 126) for i in trigs) if x is not None]
    if f3:
        per[tk] = (len(trigs), statistics.mean(f3), statistics.median(f3), len(f3))
        res3 += f3
        res6 += f6

print("15%% trailing-stop triggers across the book: %d" % sum(v[0] for v in per.values()))
print("\nforward EXCESS return after a stop trigger (vs SPY):")
if res3:
    print("  3m: mean %+.1f%%   median %+.1f%%   n=%d   share positive %.0f%%"
          % (statistics.mean(res3) * 100, statistics.median(res3) * 100, len(res3),
             100.0 * sum(1 for x in res3 if x > 0) / len(res3)))
if res6:
    print("  6m: mean %+.1f%%   median %+.1f%%   n=%d   share positive %.0f%%"
          % (statistics.mean(res6) * 100, statistics.median(res6) * 100, len(res6),
             100.0 * sum(1 for x in res6 if x > 0) / len(res6)))

print("\nby name (triggers, mean 3m excess after the stop):")
for tk, (n, m3, med3, cnt) in sorted(per.items(), key=lambda kv: -kv[1][1])[:14]:
    print("   %-6s stops=%2d  mean 3m after %+7.1f%%  median %+7.1f%%  (n=%d)" % (tk, n, m3 * 100, med3 * 100, cnt))
