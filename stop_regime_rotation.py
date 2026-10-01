#!/usr/bin/env python3
"""stop_regime_rotation.py — does the 15% trailing stop behave the same on the ROTATION names as on semis?

The book study found the stop is insurance: it helped on 21 of 28 names in 2022 and hurt on 25 of 29 in the
2025-26 uptrend. That was measured only on the semis/value book. With daily series now covering the themes
leading the market, the same rule can be tested where the money went - which is what makes the insurance
framing a finding rather than a semis anecdote.
"""
import csv, os, statistics

D = "/documents/Finance Knowledge Graph/Datasets/History/prices_daily"
GROUPS = {
    "software / cyber / cloud": ["CRM", "NOW", "INTU", "PANW", "ZS", "DDOG", "NET", "SNOW", "VEEV",
                                 "CRWD", "FTNT", "OKTA", "QLYS", "TENB", "RPD", "MSFT", "GOOGL", "META",
                                 "ORCL", "AMZN", "AAPL"],
    "energy / materials": ["XOM", "CVX", "COP", "MPC", "VLO", "EOG", "DVN", "PSX", "OXY", "FANG",
                           "FCX", "SCCO", "HBM", "TECK", "LIN", "APD", "SHW", "NUE", "STLD", "CF", "MOS"],
    "gold / life sciences": ["NEM", "AEM", "FNV", "WPM", "GOLD", "AGI", "KGC", "OR", "TMO", "DHR", "A",
                             "MTD", "BR", "RSG", "IQV", "WAT"],
    "semis (the book, for reference)": ["NVDA", "MU", "AMD", "AVGO", "MRVL", "TSM", "LITE", "MTSI",
                                        "SMTC", "AEHR", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO", "AXTI"],
}
STOP = 0.15
PERIODS = {"2022 drawdown": ("2022-01-01", "2022-12-31"),
           "2025-26 uptrend": ("2025-02-14", "2026-09-15")}


def load(tk):
    p = os.path.join(D, tk + ".csv")
    out = []
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
            try:
                out.append((r["date"][:10], float(r["close"])))
            except (ValueError, KeyError):
                pass
    return out


print("%-30s %-16s %6s %9s %10s" % ("group", "period", "n", "median", "helped"))
print("-" * 78)
for gname, names in GROUPS.items():
    for label, (start, end) in PERIODS.items():
        diffs = []
        for tk in names:
            s = [x for x in load(tk) if start <= x[0] <= end]
            if len(s) < 60:
                continue
            peak, exit_px = s[0][1], None
            for _, px in s:
                if px > peak:
                    peak = px
                if exit_px is None and px / peak - 1 <= -STOP:
                    exit_px = px
            bh = s[-1][1] / s[0][1] - 1
            st = (exit_px / s[0][1] - 1) if exit_px is not None else bh
            diffs.append(st - bh)
        if diffs:
            helped = sum(1 for d in diffs if d > 0)
            print("%-30s %-16s %6d %+8.1f%% %6d of %d"
                  % (gname, label, len(diffs), statistics.median(diffs) * 100, helped, len(diffs)))
        else:
            print("%-30s %-16s %6s %9s %10s" % (gname, label, 0, "no data", "-"))
