#!/usr/bin/env python3
"""external_audit.py - third-party evidence check on the causal map.

The vault's Datasets layer holds two externally-authored corpora that were not used in the map:
  * BuySideDigest pitches: 382 dated pitches, each with a curated `keywords` list + Bull/Bear stance
  * RhinoInvestory: 5,338 independent-analyst article titles
Neither is "the vault's own notes", so this pass does NOT upgrade `basis`. It is an independent audit:
for each name, do the outside analysts' keywords/titles corroborate the driver this map assigned, and
where do they point somewhere else? Writes `external_*` columns onto drivers.csv.
"""
import csv, json, os, re, collections, shutil

KG = "/documents/Finance Knowledge Graph"
OUT = os.path.join(KG, "Datasets", "Driver Map", "drivers.csv")
BSD = os.path.join(KG, "Datasets", "BuySideDigest", "bsd_pitches.csv")
RHINO = os.path.join(KG, "Datasets", "RhinoInvestory", "rhino_articles.json")

PARENT_OF = {"HCAPEX": "AI_CAPEX", "OPT_ATTACH": "AI_CAPEX", "SEMICAP": "AI_CAPEX", "MEM_PRICE": "MEM_CYCLE",
             "OIL": "ENERGY", "GAS": "ENERGY", "OILSERV": "ENERGY", "GOLD_RATES": "REAL_RATES",
             "ROYALTY": "REAL_RATES", "COPPER": "CHINA_INDUSTRIAL", "RATES_NIM": "RATES",
             "SMALLCAP_VAL": "RATES", "REIT_CAP": "RATES", "JAPAN_FX": "POLICY", "TARIFF": "POLICY",
             "DEFENSE_BUDGET": "POLICY", "POWER_LOAD": "POWER", "STAPLES_VOL": "CONSUMER",
             "PHARMA_PRICE": "HEALTH", "LSTOOLS": "HEALTH", "AI_SUB": "SOFTWARE", "SEAT_ARR": "SOFTWARE",
             "STEEL_IND": "INDUSTRIAL", "LITHIUM_AG": "INDUSTRIAL", "CONSUMER_HW": "CONSUMER"}
# family-level keyword test: does the outside corpus point at the same exogenous variable?
FAMILY_PAT = {
    "AI_CAPEX": r"(AI (?:capex|infrastructure|accelerator|server)|hyperscaler|data ?cent(?:re|er)|GPU|custom silicon|networking|optical|semiconductor|foundry|memory|HBM)",
    "MEM_CYCLE": r"(memory|HBM|DRAM|NAND|storage|flash)",
    "ENERGY": r"(crude|oil|natural gas|LNG|refin|upstream|rig|OPEC|commodity price)",
    "REAL_RATES": r"(gold|real rate|real yield|dollar|precious|silver)",
    "CHINA_INDUSTRIAL": r"(copper|China|metals|mining|iron ore|industrial metal)",
    "RATES": r"(interest rate|yield|rate cut|rate hike|NIM|bank|insurer|duration|Fed|credit)",
    "POLICY": r"(tariff|trade war|defen[cs]e budget|geopolitic|Japan|yen|sanction|export control)",
    "CONSUMER": r"(consumer|staple|food|beverage|retail|volume|pricing power)",
    "HEALTH": r"(pharma|drug|GLP-1|biotech|patent|FDA|clinical|lifescience|life science|diagnostic)",
    "SOFTWARE": r"(SaaS|software|subscription|ARR|cloud|cyber|seat)",
    "INDUSTRIAL": r"(steel|industrial|construction|chemical|lithium|potash|manufactur|machinery)",
    "POWER": r"(utilit|power (?:demand|grid|price)|electric|rate base|data ?cent(?:re|er) power)",
}

# --- load the external corpora ---------------------------------------------------
bsd = collections.defaultdict(list)
for r in csv.DictReader(open(BSD, encoding="utf-8")):
    bsd[r["ticker"]].append(r)
rhino = collections.defaultdict(list)
for a in json.load(open(RHINO, encoding="utf-8")):
    if a.get("ticker"):
        rhino[a["ticker"]].append(a)
print("BSD tickers: %d pitches: %d | Rhino tickers: %d articles: %d"
      % (len(bsd), sum(len(v) for v in bsd.values()), len(rhino), sum(len(v) for v in rhino.values())))

rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
supports = disagrees = silent = 0
for r in rows:
    tk = r["ticker"]
    parent = PARENT_OF.get(r["driver"], "?")
    kw_hits, word_hits = collections.Counter(), ""
    quotes = []
    for p in bsd.get(tk, [])[:40]:
        kws = (p.get("keywords") or "")
        for fam, pat in FAMILY_PAT.items():
            if re.search(pat, kws, re.I):
                kw_hits[fam] += 1
        if parent and re.search(FAMILY_PAT.get(parent, r"(?!)"), kws, re.I):
            quotes.append("BSD %s %s: %s" % (p.get("date", "")[:12], p.get("stance", ""), kws[:90]))
    titles = 0
    for a in rhino.get(tk, [])[:200]:
        t = a.get("title") or ""
        if parent and re.search(FAMILY_PAT.get(parent, r"(?!)"), t, re.I):
            titles += 1
            if len(quotes) < 2:
                quotes.append("Rhino %s: %s" % (a.get("date", "")[:10], t[:90]))
    fam_support = kw_hits.get(parent, 0) + titles
    top_other = [(f, c) for f, c in kw_hits.most_common(2) if f != parent]
    verdict = "silent"
    if fam_support > 0 and (not top_other or fam_support >= top_other[0][1]):
        verdict = "supports"
        supports += 1
    elif top_other and top_other[0][1] >= 2 and fam_support == 0:
        verdict = "disagrees"
        disagrees += 1
    else:
        silent += 1
    r["external_verdict"] = verdict
    r["external_support_hits"] = fam_support
    r["external_top_other_family"] = ("%s(%d)" % top_other[0]) if top_other else ""
    r["external_evidence"] = " | ".join(quotes[:2])[:240]

shutil.copy(OUT, "/tmp/driverwork/drivers_pre_external.csv")
with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print("\nthird-party verdicts: supports %d | disagrees %d | silent %d" % (supports, disagrees, silent))
book = [r for r in rows if r["in_book"] == "1"]
print("book: supports %d | disagrees %d | silent %d"
      % (sum(1 for r in book if r["external_verdict"] == "supports"),
         sum(1 for r in book if r["external_verdict"] == "disagrees"),
         sum(1 for r in book if r["external_verdict"] == "silent")))
print("\nDISAGREEMENTS (outside analysts point at another family) - review each:")
for r in rows:
    if r["external_verdict"] == "disagrees":
        print("  %-6s assigned=%-14s outside=%s" % (r["ticker"], r["driver"], r["external_top_other_family"]))
print("\ncorroborated examples:")
n = 0
for r in rows:
    if r["external_verdict"] == "supports" and r["evidence_strength"] == "sector/theme only":
        print("  %-6s %-14s %s" % (r["ticker"], r["driver"], r["external_evidence"][:130]))
        n += 1
        if n >= 15:
            break
