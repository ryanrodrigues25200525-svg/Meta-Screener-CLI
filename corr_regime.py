import csv, os, statistics

D = "/documents/Finance Knowledge Graph/Datasets/History/prices_daily"
SEMIS = ["AAOI", "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL",
         "NVDA", "TSM", "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO"]
VALUE = ["GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE"]
PERIODS = {"2022 stress": ("2022-01-01", "2022-12-31"),
           "2025-26 uptrend": ("2025-02-14", "2026-09-15")}


def load(tk):
    p = os.path.join(D, tk + ".csv")
    out = {}
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
            try:
                out[r["date"][:10]] = float(r["close"])
            except (ValueError, KeyError):
                pass
    return out


for label, (start, end) in PERIODS.items():
    raw = {t: {d: c for d, c in load(t).items() if start <= d <= end} for t in SEMIS + VALUE}
    usable = {t: s for t, s in raw.items() if len(s) >= 100}
    dates = sorted(set().union(*[set(s) for s in usable.values()]))
    rets = {}
    for t, s in usable.items():
        r = {}
        for i in range(1, len(dates)):
            a, b = dates[i - 1], dates[i]
            if a in s and b in s and s[a] > 0:
                r[b] = s[b] / s[a] - 1
        rets[t] = r
    common = sorted(set.intersection(*[set(r) for r in rets.values()])) if rets else []

    def corr(a, b):
        x = [rets[a][d] for d in common]
        y = [rets[b][d] for d in common]
        mx, my = statistics.mean(x), statistics.mean(y)
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        dx = sum((xi - mx) ** 2 for xi in x) ** 0.5
        dy = sum((yi - my) ** 2 for yi in y) ** 0.5
        return num / (dx * dy) if dx and dy else 0.0

    s_in = [t for t in SEMIS if t in rets]
    v_in = [t for t in VALUE if t in rets]
    if len(s_in) < 3 or len(v_in) < 3:
        print("\n=== %s ===\n   NO DATA: %d semis / %d value names have history here - not a null result."
              % (label, len(s_in), len(v_in)))
        continue
    rho_s = statistics.mean(corr(a, b) for i, a in enumerate(s_in) for b in s_in[i + 1:])
    rho_v = statistics.mean(corr(a, b) for i, a in enumerate(v_in) for b in v_in[i + 1:])
    rho_x = statistics.mean(corr(a, b) for a in s_in for b in v_in)
    print("\n=== %s (%s to %s) ===" % (label, start, end))
    print("   semis names %2d, value names %2d, common days %d" % (len(s_in), len(v_in), len(common)))
    print("   within semis      rho %+.2f" % rho_s)
    print("   within value      rho %+.2f" % rho_v)
    print("   semis vs value    rho %+.2f   <-- the offset that keeps this from being one bet" % rho_x)
