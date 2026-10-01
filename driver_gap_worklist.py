#!/usr/bin/env python3
"""write_worklist.py - the evidence-gap worklist + final accounting update.

Every mining route has now been tried for the remaining judgement-only names:
  node bodies (Key moving pieces / Competitive position), node notes:/sector:, EVERY note's
  invalidations:/catalysts:, Market Context regime edges, Claims titles, theme research notes,
  73 map/industry notes (name-placed only, strict), BuySideDigest keywords + positioning brief,
  RhinoInvestory titles. What is left is a writing job, not a mining job.
"""
import csv, os, collections

KG = "/documents/Finance Knowledge Graph"
OUT = os.path.join(KG, "Datasets", "Driver Map", "drivers.csv")
GAPS = os.path.join(KG, "Datasets", "Driver Map", "evidence-gaps.csv")

rows = list(csv.DictReader(open(OUT, encoding="utf-8")))


def per_name(r):
    return (r["basis"].startswith("vault") or r["external_verdict"] == "supports")


gaps = [r for r in rows if not per_name(r)]
with open(GAPS, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["ticker", "company", "driver", "parent_driver", "driver_variable",
                                       "theme_membership", "what_to_write"])
    w.writeheader()
    for r in sorted(gaps, key=lambda r: (r["parent_driver"], r["ticker"])):
        w.writerow({
            "ticker": r["ticker"], "company": r["company"], "driver": r["driver"],
            "parent_driver": r["parent_driver"], "driver_variable": r["driver_variable"],
            "theme_membership": r["theme_membership"],
            "what_to_write": ("Companies/%s.md: add '## Key moving pieces' bullets naming the upstream "
                              "variable (%s) and the line item it moves; Notes/: add an 'invalidations:' "
                              "kill-switch that falsifies it." % (r["company"], r["driver_variable"])),
        })
print("worklist written: %s (%d names)" % (GAPS, len(gaps)))

book = [r for r in rows if r["in_book"] == "1"]
rot = [r for r in rows if r["in_book"] == "0"]
print("\n=== FINAL EVIDENCE ACCOUNTING ===")
for lab, rs in (("book", book), ("rotation", rot), ("universe", rows)):
    pn = sum(1 for r in rs if per_name(r))
    print("%-9s n=%-4d per-name evidence %-4d (%.0f%%) | judgement-only %d"
          % (lab, len(rs), pn, 100 * pn / len(rs), len(rs) - pn))
print("\nstrength tiers:", dict(collections.Counter(r["evidence_strength"] for r in rows)))
print("gap rows by parent:",
      dict(collections.Counter(r["parent_driver"] for r in gaps)))
