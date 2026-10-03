"""daily_gaps.py — coverage-gap report for the stored daily price layer, per ticker and overall."""
import csv, glob, os, collections

D = "/documents/Finance Knowledge Graph/Datasets/History/prices_daily"
EXPECT = [str(y) for y in range(2015, 2027)]
rows = []
for p in sorted(glob.glob(os.path.join(D, "*.csv"))):
    tk = os.path.basename(p)[:-4]
    rs = list(csv.DictReader(open(p, encoding="utf-8", errors="ignore")))
    if not rs:
        continue
    yrs = collections.Counter(r["date"][:4] for r in rs)
    missing = [y for y in EXPECT if yrs.get(y, 0) < 20 and y != "2026"]
    rows.append((tk, len(rs), rs[0]["date"], rs[-1]["date"], missing))

print("daily series: %d" % len(rows))
bad = [r for r in rows if r[4]]
print("series missing a full calendar year of bars: %d" % len(bad))
print("\n%-8s %6s  %-10s %-10s %s" % ("ticker", "rows", "first", "last", "years missing"))
for tk, n, f, l, miss in sorted(bad, key=lambda r: -len(r[4]))[:25]:
    print("%-8s %6d  %-10s %-10s %s" % (tk, n, f, l, ",".join(miss)))
print("\nlast-row date distribution:")
print("  " + str(collections.Counter(r[3][:7] for r in rows).most_common(6)))
