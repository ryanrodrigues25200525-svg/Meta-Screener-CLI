import csv, os, statistics

D = "/documents/Finance Knowledge Graph/Datasets/History/prices_daily"
SEMIS = ["AAOI","AXTI","MU","SNDK","NBIS","POET","LITE","MTSI","SMTC","AEHR","MXL","NVDA","TSM","AVGO",
         "AMD","MRVL","WDC","ONTO","RMBS","TSEM","AEIS","SIMO","ALAB","CRDO","COHR","ACLS","CAMT","FORM",
         "SWKS","TER","NVMI","DIOD","AMAT","INTC","KLAC","LRCX"]
VALUE = ["GM","VTRS","VALE","CAG","GIS","HPQ","SM","PRU","NVO","PBR","PFE","ADBE"]

def series(tk):
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

print("3-month price change, daily layer, latest bar vs the bar ~63 trading days earlier:")
for label, names in (("semis/AI complex", SEMIS), ("book value half", VALUE)):
    ch = []
    for tk in names:
        s = series(tk)
        if len(s) < 70:
            continue
        ch.append((tk, (s[-1][1] / s[-64][1] - 1) * 100))
    if ch:
        vals = [c for _, c in ch]
        print("   %-18s n=%2d  median %+6.1f%%  mean %+6.1f%%  positive %d%%   (window %s to %s)"
              % (label, len(vals), statistics.median(vals), statistics.mean(vals),
                 100 * sum(1 for v in vals if v > 0) // len(vals),
                 series(names[0])[-64][0], series(names[0])[-1][0]))
        worst = sorted(ch, key=lambda x: x[1])[:5]
        best = sorted(ch, key=lambda x: -x[1])[:3]
        print("        worst: " + ", ".join("%s %+.0f%%" % (t, v) for t, v in worst))
        print("        best : " + ", ".join("%s %+.0f%%" % (t, v) for t, v in best))
