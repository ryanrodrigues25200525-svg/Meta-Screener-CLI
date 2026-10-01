#!/usr/bin/env python3
"""rename_base_metals.py - taxonomy fix: COPPER -> BASE_METALS (the shared variable is China metals demand,
and VALE's driver is iron ore, not copper). Also writes the final coverage numbers for the note/METHOD.
"""
import csv, collections

P = "/documents/Finance Knowledge Graph/Datasets/Driver Map/drivers.csv"
rows = list(csv.DictReader(open(P, encoding="utf-8")))
n = 0
for r in rows:
    if r["driver"] == "COPPER":
        r["driver"] = "BASE_METALS"
        r["driver_variable"] = "copper / iron-ore price and China industrial demand"
        r["mechanism"] = "metal price x grade x volume -> margin (China is the marginal buyer)"
        if "copper" in r["assignment_reason"].lower() or not r["assignment_reason"].startswith("override") \
           or "iron ore" in r["assignment_reason"].lower():
            r["assignment_reason"] = "override: base-metals price, China-demand driven"
        n += 1
with open(P, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("renamed COPPER -> BASE_METALS on %d rows" % n)

rows = list(csv.DictReader(open(P, encoding="utf-8")))
book = [r for r in rows if r["in_book"] == "1"]
rot = [r for r in rows if r["in_book"] == "0"]
def stats(rs):
    vault = sum(1 for r in rs if r["basis"].startswith("vault"))
    ext = sum(1 for r in rs if r["external_verdict"] == "supports")
    anye = sum(1 for r in rs if r["basis"].startswith("vault") or r["external_verdict"] == "supports")
    return vault, ext, anye, len(rs)
for label, rs in (("book", book), ("rotation", rot), ("universe", rows)):
    v, e, a, tot = stats(rs)
    print("%-9s n=%-4d vault-backed %-4d third-party %-4d ANY %-4d (%.0f%%)" % (label, tot, v, e, a, 100*a/tot))
print("\nstrength:", dict(collections.Counter(r["evidence_strength"] for r in rows)))
print("parents :", len({r["parent_driver"] for r in rows}), "drivers:", len({r["driver"] for r in rows}))
print("book drivers still judgement-only: %s"
      % (",".join(sorted(r["ticker"] for r in book if not r["basis"].startswith("vault"))) or "none"))
print("book no-evidence-at-all: %s"
      % (",".join(sorted(r["ticker"] for r in book
                         if not r["basis"].startswith("vault") and r["external_verdict"] != "supports")) or "none"))
