#!/usr/bin/env python3
"""evidence4.py - recompute evidence strength against EVERY kill-switch the vault holds per name.

Flaw fixed: the first pass read only the newest 3 notes per name and stopped once it had 3 invalidations.
GM's tariff clause is in its 2026-08-20 thesis note, while the newest note carries price-based kill-switches,
so GM scored "no vault evidence" despite the vault stating its driver explicitly. Now all notes (capped at
14) are scanned, and the evidence patterns are the broadened matching set (the ASSIGNMENTS are untouched).
"""
import csv, os, re, glob, collections, shutil

KG = "/documents/Finance Knowledge Graph"
NOTES = os.path.join(KG, "Notes")
OUT = os.path.join(KG, "Datasets", "Driver Map", "drivers.csv")

# evidence test only - broader than the assignment rules (adds the phrasings the vault actually uses)
EVID_PAT = {
    "MEM_PRICE": r"(DRAM|NAND|HBM|memory (?:price|cycle|supercycle|oversupply|contract)|bit (?:shipments|volume)|price[- ]per[- ](?:TB|bit)|NAND/AI-storage)",
    "ROYALTY": r"(royalt|stream(?:ing)? agreement|ounces? of gold equivalent)",
    "GOLD_RATES": r"(gold price|spot gold|real (?:rate|yield)|AISC|central bank (?:demand|buying)|bullion)",
    "COPPER": r"(copper|iron[- ]ore|China(?:'s)? (?:demand|stimulus)|smelter|concentrate)",
    "GAS": r"(Henry Hub|natural gas|LNG|gas[- ]weighted|Appalachian|dry gas)",
    "OIL": r"(crude|Brent|WTI|crack|refin|realised price|realized price|oil price|OPEC|upstream price)",
    "OILSERV": r"(rig count|upstream (?:capex|spend)|offshore|dayrate|frac|subsea|drilling)",
    "HCAPEX": r"(hyperscaler|data ?cent(?:re|er) capex|AI (?:capex|test|semiconductor|infrastructure)|cloud capex|neocloud|GPU|accelerator|custom (?:XPU|ASIC)|backlog compounds)",
    "OPT_ATTACH": r"(optical (?:content|attach|module|transceiver|interconnect|ramp|growth|orders)|CPO|co-packaged|photonics|laser|InP|epiwafer|design-win|ELSFP|800G|1\.6T)",
    "SEMICAP": r"(fab|capex (?:for|cycle)|wafer (?:fab )?equipment|WFE|deposition|etch|lithography|packaging|tool|backlog|AI test)",
    "RATES_NIM": r"(net interest|NIM|spread income|deposit|loan growth|credit (?:cost|provision)|curve|steepen|rate[- ]cut|rate[- ]hike|higher[- ]for[- ]long)",
    "SMALLCAP_VAL": r"(small-?cap|Russell 2000|credit spread|refinancing|discount rate)",
    "REIT_CAP": r"(cap rate|NOI|occupancy|same-store|REIT)",
    "JAPAN_FX": r"(USD/?JPY|yen|currency[- ]hedged|BOJ|Bank of Japan|Japan)",
    "TARIFF": r"(tariff|Section 232|import dut|trade (?:policy|war)|export control)",
    "DEFENSE_BUDGET": r"(backlog|appropriat|defen[cs]e (?:budget|spend)|program of record|contract award|DoD)",
    "POWER_LOAD": r"(rate base|load growth|data ?cent(?:re|er) (?:power|load|demand)|regulated|capacity market|utility|grid)",
    "STAPLES_VOL": r"(input cost|volume (?:decline|growth|pressure)|price/mix|elasticit|private label|consumer (?:pressure|weakness|trade[- ]down)|shelf|margin recovery|dividend)",
    "PHARMA_PRICE": r"(patent (?:cliff|expiry)|generic|loss of exclusivity|GLP-1|competition.{0,20}pricing|pipeline)",
    "LSTOOLS": r"(R&D (?:spend|budget)|instrument|biopharma (?:spend|capex)|laboratory|lab demand|diagnostic)",
    "AI_SUB": r"(AI (?:disruption|substitut|native)|Canva|Figma|freemium|seat|net-new ARR)",
    "SEAT_ARR": r"(net (?:new|revenue) retention|NRR|ARR|seat (?:growth|expansion)|subscription|cloud consumption|RPO|platform)",
    "STEEL_IND": r"(steel|construction demand|non-?residential|scrap|mill utilisation|industrial (?:demand|order))",
    "LITHIUM_AG": r"(lithium|spodumene|carbonate/hydroxide|crop nutrient|potash|caustic|nitrogen price|EV (?:demand|penetration))",
    "CONSUMER_HW": r"(PC (?:demand|cycle|refresh)|iPhone|device (?:refresh|cycle)|handset|ASP|units)",
}


def frontmatter(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    return (m.group(1) if m else ""), txt


def fm_list(fm, key):
    m = re.search(r"^%s:\s*(.*)$" % re.escape(key), fm, re.M)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw.startswith("["):
        items = [next((v for v in t if v), "") for t in re.findall(r"\[\[([^\]]+)\]\]|\"([^\"]+)\"|'([^']+)'", raw)]
    else:
        items = []
        grab = False
        for line in fm.splitlines():
            if re.match(r"^%s:" % re.escape(key), line):
                grab = True
                continue
            if grab:
                if re.match(r"^\s+-\s+", line):
                    items.append(re.sub(r"^\s+-\s+", "", line).strip().strip("'\""))
                elif re.match(r"^\S", line):
                    break
    return [i for i in items if i]


all_notes = collections.defaultdict(list)
for p in glob.glob(os.path.join(NOTES, "*.md")):
    base = os.path.basename(p)
    for tk in re.findall(r"(?:^|\s)([A-Z]{1,5})(?:[\s\.]|$)", base):
        all_notes[tk].append(p)
for tk in all_notes:
    all_notes[tk].sort(reverse=True)

rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
changed = 0
for r in rows:
    tk, driver = r["ticker"], r["driver"]
    pat = EVID_PAT.get(driver)
    if not pat:
        continue
    quotes, hit_note = [], ""
    for p in all_notes.get(tk, [])[:14]:
        fm, _ = frontmatter(p)
        text = " ; ".join(fm_list(fm, "invalidations") + fm_list(fm, "catalysts"))
        for part in text.split(" ; "):
            m = re.search(pat, part, re.I)
            if m:
                quotes.append(part.strip())
                hit_note = hit_note or os.path.basename(p)
                break
        if len(quotes) >= 2:
            break
    if quotes and r["evidence_strength"] == "sector/theme only":
        r["evidence_strength"] = "killswitch (later/older note)"
        r["basis"] = "vault (all-notes)"
        r["killswitch"] = quotes[0][:250]
        r["evidence_note"] = hit_note
        changed += 1
    elif quotes and not r["killswitch"]:
        r["killswitch"] = quotes[0][:250]
        r["evidence_note"] = hit_note

shutil.copy(OUT, "/tmp/driverwork/drivers_pre_allnotes.csv")
with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print("rows %d | upgraded by scanning ALL notes: %d" % (len(rows), changed))
print("basis   :", dict(collections.Counter(r["basis"] for r in rows)))
print("strength:", dict(collections.Counter(r["evidence_strength"] for r in rows)))
book = [r for r in rows if r["in_book"] == "1"]
print("book: vault-backed %d/%d" % (sum(1 for r in book if r["basis"].startswith("vault")), len(book)))
print("book still judgement-only: %s"
      % ",".join(sorted(r["ticker"] for r in book if r["basis"].startswith("analyst"))))
