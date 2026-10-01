#!/usr/bin/env python3
"""evidence6.py - harvest pass 3 (corrected): sector-primer evidence, family-level only.

The first attempt at this pass matched *mentions*, not mechanisms - it took an open-questions line
("Should SLB/BKR/... get Companies/ nodes") as causal evidence, and it matched the ticker HBM (Hudbay
Minerals, a copper name) against the Memory note, which is the ticker collision this map already warns about.
Rules now:
  * a row only qualifies if the sector map's own `companies:` array CONTAINS the name (the vault placed it
    in that map) - and for a ticker that collides with a product term, the company title must match;
  * the quoted line must state a mechanism (contains the driver pattern) and must not come from a
    question/to-do/verification section, nor be a "disk gap" note;
  * the tier is `sector-primer (family-level)`: it supports the DRIVER FAMILY, not that name's sensitivity,
    and `basis` stays `analyst + sector primer` so it is never counted as per-name vault evidence.
"""
import csv, os, re, glob, collections, shutil

KG = "/documents/Finance Knowledge Graph"
NOTES, COMP, THEMES = (os.path.join(KG, x) for x in ("Notes", "Companies", "Themes"))
OUT = os.path.join(KG, "Datasets", "Driver Map", "drivers.csv")
SNAP = "/tmp/driverwork/drivers_pre_pass3.csv"      # state before the bad pass (94 vault-backed)

# tickers that also read as a product/term - they must match on company title, never on the bare ticker
COLLIDING = {"HBM", "A", "ON", "IT", "AI", "SO", "ES", "D", "C", "MS", "GS", "TDG", "NET", "S"}

EVID_PAT = {
    "POWER_LOAD": r"(rate base|load growth|data ?cent(?:re|er) (?:power|load|demand)|regulated (?:return|asset)|capacity market|interconnection|grid|electric(?:ity)? demand|power demand)",
    "GOLD_RATES": r"(gold price|spot gold|real (?:rate|yield)|AISC|central bank (?:demand|buying)|safe[- ]haven|bullion)",
    "OIL": r"(crude|Brent|WTI|crack|refin(?:ing|ery)? margin|realised price|realized price|oil price|barrel|OPEC)",
    "GAS": r"(Henry Hub|natural gas price|LNG|gas[- ]weighted|liquefaction|netback)",
    "OILSERV": r"(rig count|upstream (?:capex|spend)|offshore|dayrate|frac|subsea|drilling|oilfield service)",
    "RATES_NIM": r"(net interest|NIM|spread income|deposit (?:beta|franchise)|loan growth|credit (?:cost|provision)|curve|steepen|rate[- ]cut|rate[- ]hike|policy rate)",
    "SMALLCAP_VAL": r"(small-?cap|Russell 2000|credit spread|refinancing|discount rate|value (?:factor|spread))",
    "DEFENSE_BUDGET": r"(backlog|appropriat|defen[cs]e (?:budget|spend|outlays)|program(?:me)? of record|contract award|DoD|book[- ]to[- ]bill)",
    "LSTOOLS": r"(R&D (?:spend|budget)|instrument|biopharma (?:spend|capex)|laboratory|diagnostic|clinical)",
    "PHARMA_PRICE": r"(patent (?:cliff|expiry)|generic|loss of exclusivity|GLP-1|pipeline|drug pricing|reimbursement)",
    "SEAT_ARR": r"(net (?:new|revenue) retention|NRR|ARR |subscription|cloud consumption|RPO|seat)",
    "AI_SUB": r"(AI (?:disruption|substitut|native)|freemium|seat (?:decline|erosion)|net-new ARR)",
    "INDUSTRIAL_PAT": r"(industrial (?:demand|production|orders)|manufacturing PMI|automation|capex cycle)",
    "STEEL_IND": r"(steel|construction demand|non-?residential|scrap|mill utilisation)",
    "LITHIUM_AG": r"(lithium|spodumene|crop nutrient|potash|caustic|nitrogen price|battery-grade)",
    "MEM_PRICE": r"(DRAM|NAND|memory (?:price|cycle|contract)|bit (?:shipments|volume))",
    "BASE_METALS": r"(copper|iron[- ]ore|smelter|concentrate|metal price)",
    "JAPAN_FX": r"(USD/?JPY|yen|currency[- ]hedged|BOJ|Japan(?:ese)? (?:exporter|market|equit|governance))",
    "STAPLES_VOL": r"(input cost|volume (?:decline|growth)|price/mix|private label|gross margin|pricing power)",
    "CONSUMER_HW": r"(PC (?:demand|cycle)|iPhone|device (?:refresh|cycle)|handset|units)",
}
BAD_SECTIONS = r"(?i)^##+ *(open question|review|next step|gaps|what.s still open|follow|method)"
BAD_TEXT = r"(?i)(\bshould\b|\bdisk gap\b|\bunverified\b|\?\s*$|get Companies/ nodes)"

# restore the pre-pass-3 state
shutil.copy(SNAP, OUT)
rows = list(csv.DictReader(open(OUT, encoding="utf-8")))

# company title + sector-map membership
title_of, sector_maps = {}, {}
for p in glob.glob(os.path.join(NOTES, "* map research.md")):
    n = os.path.basename(p)[:-3]
    head = open(p, encoding="utf-8", errors="ignore").read()
    mem = re.search(r"^companies:\s*(.*)$", head, re.M | re.S)
    names = set(re.findall(r"\[\[([^\]]+)\]\]", mem.group(1)[:4000])) if mem else set()
    sector_maps[n] = (head, names)
for p in glob.glob(os.path.join(COMP, "*.md")):
    head = open(p, encoding="utf-8", errors="ignore").read(1200)
    m = re.search(r'^ticker:\s*"?([A-Za-z0-9\.\-]+)"?', head, re.M)
    if m:
        title_of.setdefault(m.group(1), os.path.basename(p)[:-3])

upgraded, rejected = 0, []
for r in rows:
    if r["basis"].startswith("vault"):
        continue
    tk, driver = r["ticker"], r["driver"]
    pat = EVID_PAT.get(driver) or EVID_PAT.get("INDUSTRIAL_PAT" if driver in ("STEEL_IND", "LITHIUM_AG") else "")
    if not pat:
        continue
    company = title_of.get(tk, r["company"])
    hit = None
    for nname, (head, members) in sector_maps.items():
        # the vault must have placed this NAME in that sector map
        placed = company in members or (tk not in COLLIDING and tk in members)
        if not placed:
            continue
        section = ""
        for line in head.splitlines():
            if re.match(r"^##+ ", line):
                section = line
            if len(line) < 40 or re.match(BAD_SECTIONS, section or ""):
                continue
            if company not in line and (tk in COLLIDING or tk not in line):
                continue
            if re.search(BAD_TEXT, line):
                continue
            if re.search(pat, line, re.I):
                hit = (nname, re.sub(r"\s+", " ", line.strip())[:300])
                break
        if hit:
            break
    if hit:
        r["pass3_source"] = "Notes/%s.md (sector primer)" % hit[0]
        r["pass3_text"] = hit[1]
        r["evidence_strength"] = "sector-primer (family-level)"
        r["basis"] = "analyst + sector primer"
        upgraded += 1
    else:
        rejected.append(tk)

fields = list(rows[0].keys())
for r in rows:
    for k in r:
        if k not in fields:
            fields.append(k)
with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

print("corrected pass 3: %d rows got family-level sector-primer evidence" % upgraded)
print("basis   :", dict(collections.Counter(r["basis"] for r in rows)))
book = [r for r in rows if r["in_book"] == "1"]
rot = [r for r in rows if r["in_book"] == "0"]
for lab, rs in (("book", book), ("rotation", rot), ("universe", rows)):
    per_name = sum(1 for r in rs if r["basis"].startswith("vault"))
    anyev = sum(1 for r in rs if r["basis"].startswith("vault") or r["external_verdict"] == "supports")
    primer = sum(1 for r in rs if "sector primer" in r["basis"])
    print("%-9s per-name vault %3d | any per-name %3d | +sector primer %3d | naked %3d"
          % (lab, per_name, anyev, primer, len(rs) - anyev - primer))
print("\nnaked rows (no per-name evidence and no family primer): %s"
      % (",".join(sorted(r["ticker"] for r in rows
                         if not r["basis"].startswith("vault") and r["external_verdict"] != "supports"
                         and "sector primer" not in r["basis"])) or "none"))
print("\ncollision guard exercised: HBM ->", next((r["driver"] + " / " + r["basis"] for r in rows if r["ticker"] == "HBM"), "n/a"))
print("\nsample sector-primer rows:")
n = 0
for r in rows:
    if "sector primer" in r["basis"]:
        print("  %-6s %-13s %-38s %s" % (r["ticker"], r["driver"], r["pass3_source"][6:44], r["pass3_text"][:100]))
        n += 1
        if n >= 12:
            break
