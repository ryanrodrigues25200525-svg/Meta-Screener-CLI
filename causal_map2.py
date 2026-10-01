#!/usr/bin/env python3
"""causal_map2.py - causal driver map, v2: sector-scoped, anchored, scored.

For every book + rotation-set name record: upstream variable -> mechanism -> sign -> lag -> the name's
own falsification test, with the vault sentence that supports it.

Improvements over v1 (which mis-assigned industrial gases to memory and Albemarle to royalties):
  * DRIVER ONLY COUNTS IF ITS PATTERN HITS THE RIGHT EVIDENCE BAND: node "Key moving pieces" (weight 3),
    node `notes:`/sector (weight 2), the name's own kill-switch/catalyst (weight 1).
  * SECTOR GATE: a name is only eligible for drivers its sector/theme can plausibly have.
  * THEME FALLBACK for nodes with no causal text (empty "Key moving pieces").
  * Explicit OVERRIDES for vehicles/edge cases, each with a reason.
Writes /tmp/driverwork/drivers.csv + prints the audit table.
"""
import csv, os, re, glob, collections

KG = "/documents/Finance Knowledge Graph"
COMP, NOTES = os.path.join(KG, "Companies"), os.path.join(KG, "Notes")
ROSTER = "/tmp/driverwork/roster.csv"

DRIVERS = {
    "HCAPEX":      ("hyperscaler data-centre capex ($)", "capex budget -> accelerator / networking / neocloud order flow -> backlog -> revenue", "+", "1-3 q", "AI_CAPEX"),
    "OPT_ATTACH":  ("optical content per AI rack (port speed x lanes)", "attach rate -> transceiver / laser / InP substrate demand -> revenue", "+", "2-4 q", "AI_CAPEX"),
    "MEM_PRICE":   ("DRAM / NAND / HBM contract price", "price x bit volume -> revenue and gross margin (price-taker at the margin)", "+/-", "1 q", "MEM_CYCLE"),
    "SEMICAP":     ("fab + memory equipment capex", "customer capex plan -> tool orders -> backlog -> revenue", "+", "2-3 q", "AI_CAPEX"),
    "OIL":         ("Brent / WTI + crack spread", "realised price x volume -> FCF and dividend capacity", "+", "same q", "ENERGY"),
    "GAS":         ("Henry Hub / LNG netback", "realised gas price -> FCF (gas-weighted producer)", "+", "same q", "ENERGY"),
    "OILSERV":     ("rig count / upstream capex", "activity -> utilisation and pricing -> revenue, EBITDA", "+ (lags oil)", "1-2 q", "ENERGY"),
    "GOLD_RATES":  ("real yields (TIPS) and the US dollar", "real rates down / USD down -> gold price -> realised price, AISC margin, reserve NPV", "- on real rates", "1-2 q", "REAL_RATES"),
    "ROYALTY":     ("gold price x ounces on royalty/stream", "revenue royalty with near-fixed costs -> margin is a levered gold price", "+", "same q", "REAL_RATES"),
    "COPPER":      ("copper price / China industrial demand", "metal price x grade x volume -> margin", "+", "same q", "CHINA_INDUSTRIAL"),
    "RATES_NIM":   ("policy path + curve steepness", "rate path -> NIM / spread income / credit cost -> EPS and book value", "+ when steeper", "1-2 q", "RATES"),
    "SMALLCAP_VAL":("domestic rates + credit spreads", "discount rate and refinancing cost -> small-cap value factor", "+ when rates fall", "1-2 q", "RATES"),
    "REIT_CAP":    ("cap rates / long yields", "cap rate -> NAV and cost of capital -> total return", "- on yields", "1-2 q", "RATES"),
    "JAPAN_FX":    ("USD/JPY (+ BOJ path)", "yen -> exporter earnings translation (unhedged) or hedge cost (hedged); BOJ -> domestic multiples", "+/-", "1-2 q", "POLICY"),
    "TARIFF":      ("trade policy / tariff rate", "tariff -> COGS and unit economics -> margin or volume", "-", "1-2 q", "POLICY"),
    "DEFENSE_BUDGET":("defence appropriations and backlog", "budget authority -> backlog -> revenue conversion", "+", "2-6 q", "POLICY"),
    "POWER_LOAD":  ("data-centre load growth + regulated rate base", "load growth -> capex and rate base -> regulated EPS", "+", "2-6 q", "POWER"),
    "STAPLES_VOL": ("consumer volumes + input costs", "volume and price/mix vs input cost -> gross margin -> FCF and dividend cover", "+/-", "1-2 q", "CONSUMER"),
    "PHARMA_PRICE":("generic deflation / patent cliff / GLP-1 competition", "price erosion and loss of exclusivity -> revenue base -> FCF", "-", "4-8 q", "HEALTH"),
    "LSTOOLS":     ("biopharma R&D spend", "R&D budget -> instrument and consumable demand -> revenue", "+", "1-2 q", "HEALTH"),
    "AI_SUB":      ("AI substitution of software seats", "AI-native competitor -> net-new ARR and seat growth -> subscription revenue", "-", "2-4 q", "SOFTWARE"),
    "SEAT_ARR":    ("enterprise seat / cloud consumption budget", "budget -> net-new ARR and net retention -> subscription revenue", "+", "1-2 q", "SOFTWARE"),
    "STEEL_IND":   ("industrial demand + import policy", "volume x spread -> EBITDA", "+/-", "1-2 q", "INDUSTRIAL"),
    "LITHIUM_AG":  ("lithium / crop-nutrient prices", "commodity price -> realised price -> margin", "+/-", "1-2 q", "INDUSTRIAL"),
    "CONSUMER_HW": ("device refresh cycle + tariffs", "unit refresh and ASP x China supply chain cost -> revenue and margin", "+/-", "1-2 q", "CONSUMER"),
    "UNKNOWN":     ("unclassified", "no causal statement found in the vault", "?", "-", "UNKNOWN"),
}

# anchored patterns: each must describe the upstream variable, not a downstream effect
PATTERNS = {
    "MEM_PRICE":   r"\b(DRAM|NAND|HBM|memory (?:prices?|contract|cycle|supercycle)|bit (?:shipments|volume|growth)|flash pricing|price[- ]per[- ](?:TB|bit))\b",
    "ROYALTY":     r"\b(royalt(?:y|ies)|stream(?:ing)? agreement|ounces? of gold equivalent|GEOs)\b",
    "GOLD_RATES":  r"\b(gold price|spot gold|real (?:rates|yields)|AISC|central bank (?:demand|buying)|bullion|gold[- ]linked)\b",
    "COPPER":      r"\b(copper (?:price|demand|equivalent)|China(?:'s)? (?:demand|stimulus|property|construction)|smelter|concentrate (?:market|terms)|TC/?RC)\b",
    "GAS":         r"\b(Henry Hub|natural gas (?:price|demand)|LNG (?:netback|price|offtake)|gas[- ]weighted|Appalachian|dry gas|gas marketing)\b",
    "OIL":         r"\b(crude|Brent|WTI|crack spread|refin(?:ing|ery) margin|realised price|realized price|oil price|upstream price|production (?:growth|quota)|OPEC)\b",
    "OILSERV":     r"\b(rig count|upstream (?:capex|spend)|offshore day ?rate|dayrates?|utilisation|utilization|drilling activity|frac(?:ing)? (?:spread|demand)|subsea)\b",
    "HCAPEX":      r"\b(hyperscaler|data ?cent(?:re|er) capex|AI capex|cloud capex|neocloud|GPU (?:demand|supply|rental)|accelerator (?:demand|orders)|custom (?:XPU|ASIC) (?:demand|programme|program))\b",
    "OPT_ATTACH":  r"\b(optical (?:content|attach|module|transceiver|interconnect)|CPO|co-packaged|silicon photonics|DFB|EML|laser (?:demand|pricing|source)|InP|epiwafer|800G|1\.6T|ELSFP)\b",
    "SEMICAP":     r"\b(fab (?:buildout|capex|spend|construction)|wafer fab equipment|WFE|deposition|etch(?:ing)?|lithography|memory capex|foundry capex|advance(?:d)? packaging (?:capex|equipment)|tool (?:orders|backlog))\b",
    "RATES_NIM":   r"\b(net interest (?:margin|income)|NIM|spread income|deposit (?:beta|costs|franchise)|loan growth|credit (?:cost|provision|normalisation)|reserve (?:build|release)|curve steepen\w*|policy rate path|higher[- ]for[- ]long(?:er)?)\b",
    "JAPAN_FX":    r"\b(USD/?JPY|yen|currency[- ]hedged|hedge (?:cost|benefit)|BOJ|Bank of Japan|Japan(?:ese)? (?:exporter|equit|market|CPI|wage))\b",
    "TARIFF":      r"\b(tariff|Section 232|import dut(?:y|ies)|trade (?:policy|barrier)|export control|subsid(?:y|ies) (?:for|to) (?:fabs|domestic))\b",
    "AI_SUB":      r"\b(AI (?:disruption|substitut\w+|competition|native)|Canva|Figma|freemium|seat (?:decline|erosion|pressure)|net-new ARR (?:decline|pressure))\b",
    "SEAT_ARR":    r"\b(net (?:new|revenue) retention|NRR|ARR\b|seat growth|subscription (?:revenue|growth)|cloud consumption|remaining performance obligation|RPO|consumption (?:growth|budget)|platform (?:consolidation|adoption))\b",
    "STAPLES_VOL": r"\b(input cost|volume (?:decline|growth|pressure)|price/mix|elasticit|shelf (?:space|stability)|private label|consumer (?:pressure|weakness|trade[- ]down)|promotional)\b",
    "PHARMA_PRICE":r"\b(patent (?:cliff|expiry|expiration)|generic (?:deflation|competition|entry|prices?)|loss of exclusivity|LOE\b|GLP-1|indication (?:expansion|readout)|pipeline (?:readout|failure|success))\b",
    "STEEL_IND":   r"\b(steel (?:price|spread|demand|imports)|construction demand|non-?residential|scrap (?:price|spread)|mill utilisation|sheet (?:price|demand))\b",
    "DEFENSE_BUDGET": r"\b(backlog|appropriat\w+|defen[cs]e (?:budget|spend|outlays)|program(?:me)? of record|contract award|DoD|supplemental funding)\b",
    "POWER_LOAD":  r"\b(rate base|load growth|data ?cent(?:re|er) (?:power|load|demand)|regulated (?:return|asset|utility)|capacity market|interconnection queue|power (?:purchase|PPA))\b",
    "LITHIUM_AG":  r"\b(lithium (?:price|cycle|demand)|spodumene|carbonate/hydroxide|crop nutrient|potash|caustic|nitrogen price|battery-grade|EV (?:demand|penetration))\b",
    "LSTOOLS":     r"\b(R&D (?:spend|budget)|instrument (?:placement|demand|order)|biopharma (?:spend|capex|R&D)|lab(?:oratory)? (?:demand|instrument)|pharma (?:capex|R&D))\b",
    "SMALLCAP_VAL":r"\b(small-?cap value|Russell 2000|credit spread|refinancing (?:risk|cost)|domestic (?:demand|economy))\b",
    "REIT_CAP":    r"\b(cap rate|NOI\b|occupancy|same-store|FFO|REIT)\b",
    "CONSUMER_HW": r"\b(iPhone|device (?:refresh|cycle)|PC (?:demand|cycle|refresh)|smartphone|handset|ASP\b|installed base|units? (?:decline|growth) (?:in )?(?:PC|device))\b",
}

# a name must plausibly have the driver: sector/theme token gate
GATE = {
    "MEM_PRICE":   r"(memory|dram|nand|hbm|storage|semiconduct|controller|interface)",
    "ROYALTY":     r"(gold|precious|royalt|stream|mining|miner)",
    "GOLD_RATES":  r"(gold|precious|mining|miner|metals)",
    "COPPER":      r"(copper|mining|miner|metals|materials|basic)",
    "GAS":         r"(energy|gas|oil|exploration|production|pipeline)",
    "OIL":         r"(energy|oil|gas|exploration|production|refin|integrated|upstream)",
    "OILSERV":     r"(oil services|energy equipment|services|drilling|offshore|oil)",
    "HCAPEX":      r"(semiconduct|AI|cloud|infrastructure|software|internet|technolog|foundry|networking|data)",
    "OPT_ATTACH":  r"(optical|photonic|semiconduct|networking|laser|interconnect|substrate|component)",
    "SEMICAP":     r"(semiconduct|equipment|foundry|memory|materials|gases|packaging|metrology|test)",
    "RATES_NIM":   r"(financ|bank|insur|capital markets|consumer finance|asset manage)",
    "SMALLCAP_VAL":r"(etf|fund|index|value)",
    "REIT_CAP":    r"(reit|real estate)",
    "JAPAN_FX":    r"(japan|etf|fund|index)",
    "TARIFF":      r"(auto|steel|aluminum|industrial|manufactur|semiconduct|machinery)",
    "DEFENSE_BUDGET": r"(defen[cs]e|aerospace|government|space|security)",
    "POWER_LOAD":  r"(utilit|power|electric|energy|reit|infrastructure)",
    "STAPLES_VOL": r"(consumer staples|food|beverage|retail|household|packaged)",
    "PHARMA_PRICE":r"(pharma|biotech|health|drug|medicine|care)",
    "LSTOOLS":     r"(life sciences|tools|diagnostic|health|lab|biotech)",
    "AI_SUB":      r"(software|internet|application|saas)",
    "SEAT_ARR":    r"(software|internet|cyber|saas|cloud|application)",
    "STEEL_IND":   r"(steel|metals|materials|basic|industrial|manufactur)",
    "LITHIUM_AG":  r"(lithium|mining|materials|chemicals|agricultur|fertilizer|basic)",
    "CONSUMER_HW": r"(hardware|technology|consumer|electronics|device)",
}

# theme -> driver fallback when a node has no causal text at all
THEME_FALLBACK = {
    "Copper Miners": "COPPER", "Gold Miners": "GOLD_RATES", "Oil Services": "OILSERV",
    "Life Sciences Tools": "LSTOOLS", "Utilities": "POWER_LOAD", "Financials": "RATES_NIM",
    "Defense": "DEFENSE_BUDGET", "Oil & gas": "OIL", "Energy": "OIL",
    "Exploration & Production": "OIL", "Materials": "COPPER", "REITs": "REIT_CAP",
    "Small-cap value": "SMALLCAP_VAL", "Japan": "JAPAN_FX", "Cybersecurity": "SEAT_ARR",
    "Software & SaaS": "SEAT_ARR", "Hyperscalers": "HCAPEX", "Semis & Semicapital Equipment": "SEMICAP",
    "AI infrastructure": "HCAPEX", "Information Technology": "HCAPEX",
}

# hand decisions after review: ticker -> (driver, reason)
OVERRIDES = {
    "FNV": ("ROYALTY", "streaming/royalty model - revenue royalty, near-fixed cost, levered gold price"),
    "WPM": ("ROYALTY", "streaming/royalty model"),
    "OR":  ("ROYALTY", "royalty/streaming model"),
    "AAPL": ("CONSUMER_HW", "device refresh + China supply chain; not a copper or AI-capex name"),
    "DXJ": ("JAPAN_FX", "currency-hedged Japan - the FX move is the vehicle's design"),
    "EWJ": ("JAPAN_FX", "unhedged Japan - yen translation is the first-order driver"),
    "HEWJ": ("JAPAN_FX", "currency-hedged Japan"),
    "DXJS": ("JAPAN_FX", "currency-hedged Japan small-cap"),
    "EWV": ("JAPAN_FX", "inverse Japan - driver is the same, sign inverted"),
    "AVUV": ("SMALLCAP_VAL", "factor ETF"), "IWN": ("SMALLCAP_VAL", "factor ETF"),
    "IJR": ("SMALLCAP_VAL", "factor ETF"), "SLYV": ("SMALLCAP_VAL", "factor ETF"),
    "LIN": ("SEMICAP", "industrial gases - fab buildout/electronics purity drive on-site wins"),
    "APD": ("SEMICAP", "industrial gases - fab buildout drives on-site wins"),
    "ALB": ("LITHIUM_AG", "lithium price cycle is the driver; the 'critical minerals for semis' theme is not"),
    "HBM": ("COPPER", "Hudbay Minerals - copper miner (ticker collision with the HBM memory term)"),
    "TECK": ("COPPER", "copper/steelmaking coal miner"),
    "SCCO": ("COPPER", "pure copper producer"),
    "QCOM": ("CONSUMER_HW", "handset modem/SoC - device cycle, not royalty-on-gold"),
    "TXN": ("STEEL_IND", "analog/industrial demand - industrial and auto order rates"),
    "AEIS": ("SEMICAP", "deposition power subsystems - fab capex"),
    "AEHR": ("SEMICAP", "test/burn-in equipment - AI test capex"),
    "ONTO": ("SEMICAP", "metrology/inspection - advanced packaging capex"),
    "AMAT": ("SEMICAP", "WFE"), "LRCX": ("SEMICAP", "WFE"), "KLAC": ("SEMICAP", "WFE"),
    "ASML": ("SEMICAP", "lithography WFE"),
    "DHR": ("LSTOOLS", "life sciences instruments"), "TMO": ("LSTOOLS", "life sciences tools"),
    "A": ("LSTOOLS", "life sciences tools"), "MTD": ("LSTOOLS", "life sciences tools"),
    "WAT": ("LSTOOLS", "life sciences tools"), "IQV": ("LSTOOLS", "clinical research demand"),
    "BR": ("STAPLES_VOL", "no sector in provider profile; treat as unclassified-financial-services placeholder"),
    "RSG": ("STAPLES_VOL", "waste services - volume/price, not a life-sciences driver"),
    "GNSS": ("LSTOOLS", "life sciences tools"), "NTRA": ("LSTOOLS", "diagnostics"),
    "PKI": ("LSTOOLS", "life sciences tools (PerkinElmer lineage)"),
    "MS": ("RATES_NIM", "investment bank - capital markets + spread income"),
    "BLK": ("RATES_NIM", "asset manager - AUM scales with markets and flows"),
    "SCHW": ("RATES_NIM", "broker/bank - NIM is the primary driver"),
    "AXP": ("RATES_NIM", "card lender - NIM and credit costs"),
    "GS": ("RATES_NIM", "investment bank"),
    "GM": ("TARIFF", "tariff cost clause is the only named kill-switch driver"),
    "HPQ": ("CONSUMER_HW", "PC demand + memory input cost"),
    "SWN": ("GAS", "dry-gas Appalachian producer"), "EQT": ("GAS", "dry-gas producer"),
    "AR": ("GAS", "Appalachian gas"), "CHRD": ("OIL", "oil-weighted Bakken"),
    "CTRA": ("GAS", "gas-weighted (no price series available)"),
    "OVV": ("OIL", "oil-weighted"), "DVN": ("OIL", "oil-weighted"), "FANG": ("OIL", "oil-weighted Permian"),
    "OXY": ("OIL", "oil-weighted"), "EOG": ("OIL", "oil-weighted"), "COP": ("OIL", "oil-weighted"),
    "XOM": ("OIL", "integrated - crude dictates upstream and refining"),
    "CVX": ("OIL", "integrated"), "MPC": ("OIL", "refiner - crack spread is the driver"),
    "VLO": ("OIL", "refiner - crack spread"), "PSX": ("OIL", "refiner"),
    "SM": ("OIL", "Permian E&P"), "PBR": ("OIL", "integrated + Brazil policy"),
    "SLB": ("OILSERV", "oil services"), "HAL": ("OILSERV", "oil services"), "BKR": ("OILSERV", "oil services"),
    "FTI": ("OILSERV", "subsea equipment"), "NOV": ("OILSERV", "drilling equipment"),
    "CHX": ("OILSERV", "production chemicals"), "PUMP": ("OILSERV", "frac services"),
    "OII": ("OILSERV", "subsea robotics"), "TDW": ("OILSERV", "offshore vessels"),
    "RIG": ("OILSERV", "offshore drilling dayrates"),
    "VALE": ("COPPER", "iron ore + copper diversified miner - commodity price is the driver"),
    "FCX": ("COPPER", "pure copper producer"),
    "NEM": ("GOLD_RATES", "gold miner - real rates and the dollar"),
    "AEM": ("GOLD_RATES", "gold miner"), "KGC": ("GOLD_RATES", "gold miner"), "AUY": ("GOLD_RATES", "gold miner (Yamana)"),
    "AGI": ("GOLD_RATES", "gold miner"), "EGO": ("GOLD_RATES", "gold miner"),
    "GOLD": ("GOLD_RATES", "Barrick lineage (ticker now Gold.com per the vault's reuse note)"),
    "NUE": ("STEEL_IND", "steel mill"), "STLD": ("STEEL_IND", "steel mill"),
    "SHW": ("LITHIUM_AG", "coatings - construction/industrial demand input cost"),
    "CF": ("LITHIUM_AG", "nitrogen fertiliser - crop and gas input"), "MOS": ("LITHIUM_AG", "phosphate/potash"),
    "DHR2": ("LSTOOLS", ""),
    "CAG": ("STAPLES_VOL", "packaged food - margin/volume"), "GIS": ("STAPLES_VOL", "packaged food"),
    "PRU": ("RATES_NIM", "insurer - spread income"), "JPM": ("RATES_NIM", "bank"), "BAC": ("RATES_NIM", "bank"),
    "WFC": ("RATES_NIM", "bank"), "C": ("RATES_NIM", "bank"), "PNC": ("RATES_NIM", "bank"),
    "ADBE": ("AI_SUB", "AI substitution of seats - sign is negative"), "CRM": ("SEAT_ARR", "cloud seat/consumption budget"),
    "NOW": ("SEAT_ARR", "ITSM seat budget"), "INTU": ("SEAT_ARR", "SMB subscription"), "SNOW": ("SEAT_ARR", "cloud consumption"),
    "DDOG": ("SEAT_ARR", "usage-based cloud consumption"), "NET": ("SEAT_ARR", "cloud/edge consumption"),
    "VEEV": ("SEAT_ARR", "life-sciences SaaS seats"),
    "MSFT": ("HCAPEX", "Azure capex + cloud - dual with SEAT_ARR, capex is the causal swing"),
    "GOOGL": ("HCAPEX", "capex + search; capex is the AI swing"), "AMZN": ("HCAPEX", "AWS capex"),
    "META": ("HCAPEX", "capex is the AI swing"), "ORCL": ("HCAPEX", "OCI capex"),
    "NVDA": ("HCAPEX", "accelerator demand is hyperscaler capex"), "AVGO": ("HCAPEX", "custom XPU orders = hyperscaler capex"),
    "AMD": ("HCAPEX", "DC accelerator demand"), "TSM": ("HCAPEX", "leading-edge foundry demand"),
    "MRVL": ("HCAPEX", "custom AI silicon"), "NBIS": ("HCAPEX", "GPU cloud capacity"),
    "MU": ("MEM_PRICE", "memory pricing"), "SNDK": ("MEM_PRICE", "NAND pricing"), "WDC": ("MEM_PRICE", "nearline HDD pricing"),
    "RMBS": ("MEM_PRICE", "HBM interface IP royalties"), "SIMO": ("MEM_PRICE", "NAND controllers"),
    "AAOI": ("OPT_ATTACH", "DC transceivers"), "LITE": ("OPT_ATTACH", "lasers/transceivers"), "MTSI": ("OPT_ATTACH", "optical content per server"),
    "SMTC": ("OPT_ATTACH", "DC optical ramp"), "POET": ("OPT_ATTACH", "CPO volume adoption"), "AXTI": ("OPT_ATTACH", "InP substrate"),
    "MXL": ("OPT_ATTACH", "optical + broadband"), "INTC": ("HCAPEX", "foundry + DC CPU"),
    "TSEM": ("SEMICAP", "specialty foundry capacity/utilisation"),
    "HII": ("DEFENSE_BUDGET", "shipbuilding backlog"), "LMT": ("DEFENSE_BUDGET", "backlog"),
    "RTX": ("DEFENSE_BUDGET", "backlog"), "NOC": ("DEFENSE_BUDGET", "backlog"), "GD": ("DEFENSE_BUDGET", "backlog"),
    "LHX": ("DEFENSE_BUDGET", "backlog"), "TDG": ("DEFENSE_BUDGET", "aftermarket + OEM"), "LDOS": ("DEFENSE_BUDGET", "services backlog"),
    "BAH": ("DEFENSE_BUDGET", "government consulting"), "KTOS": ("DEFENSE_BUDGET", "drones/targets"), "AVAV": ("DEFENSE_BUDGET", "drones"),
    "LUNR": ("DEFENSE_BUDGET", "space/NASA"), "NEE": ("POWER_LOAD", "utility rate base"), "DUK": ("POWER_LOAD", "utility"),
    "SO": ("POWER_LOAD", "utility"), "D": ("POWER_LOAD", "utility"), "AEP": ("POWER_LOAD", "utility"),
    "EXC": ("POWER_LOAD", "utility"), "WEC": ("POWER_LOAD", "utility"), "ES": ("POWER_LOAD", "utility"),
    "ED": ("POWER_LOAD", "utility"), "FE": ("POWER_LOAD", "utility"),
    "VTRS": ("PHARMA_PRICE", "generic deflation"), "PFE": ("PHARMA_PRICE", "patent cliff"), "NVO": ("PHARMA_PRICE", "GLP-1 competition"),
    "CRWD": ("SEAT_ARR", "security platform ARR"), "PANW": ("SEAT_ARR", "security platform ARR"),
    "FTNT": ("SEAT_ARR", "firewall refresh/ARR"), "ZS": ("SEAT_ARR", "zero-trust seats"), "S": ("SEAT_ARR", "endpoint seats"),
    "OKTA": ("SEAT_ARR", "identity seats"), "QLYS": ("SEAT_ARR", "vuln management seats"), "TENB": ("SEAT_ARR", "exposure mgmt seats"),
    "RPD": ("SEAT_ARR", "security seats"),
    "XOM2": ("OIL", ""),
}


def frontmatter(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    return (m.group(1) if m else ""), txt


def section(body, heading):
    m = re.search(r"^##+ %s\s*$(.*?)(?=^##+ |\Z)" % re.escape(heading), body, re.M | re.S)
    return m.group(1).strip() if m else ""


def fm_field(fm, key):
    m = re.search(r"^%s:\s*(.*)$" % re.escape(key), fm, re.M)
    return m.group(1).strip() if m else ""


def split_list(raw):
    out = []
    for part in re.findall(r"\[\[([^\]]+)\]\]|\"([^\"]+)\"|'([^']+)'|([^,\[\]\s][^,\[\]]*)", raw or ""):
        v = next((x for x in part if x), "").strip().strip("'\"")
        if v:
            out.append(v)
    return out


node, notes_by_ticker = {}, collections.defaultdict(list)
for p in glob.glob(os.path.join(COMP, "*.md")):
    fm, body = frontmatter(p)
    tk = fm_field(fm, "ticker").strip('"')
    if tk and tk not in node:
        node[tk] = {"path": p, "fm": fm, "body": body}
for p in glob.glob(os.path.join(NOTES, "*.md")):
    base = os.path.basename(p)
    for tk in node:
        if re.search(r"(?:^|\s)%s(?:[\s\.]|$)" % re.escape(tk), base):
            notes_by_ticker[tk].append(p)
for tk in notes_by_ticker:
    notes_by_ticker[tk].sort(reverse=True)

rows = []
for r in csv.DictReader(open(ROSTER, encoding="utf-8")):
    tk = r["ticker"]
    nd = node.get(tk, {})
    body, fm = nd.get("body", ""), nd.get("fm", "")
    kp = section(body, "Key moving pieces")
    kp_bullets = [re.sub(r"^[-\s]+", "", b).strip() for b in kp.splitlines() if b.strip().startswith("-")][:8]
    node_notes = fm_field(fm, "notes").strip('"')
    sector = r.get("sector", "")
    theme_membership = r.get("theme_membership", "")

    kill, cats, note_used = [], [], ""
    for p in notes_by_ticker.get(tk, [])[:3]:
        nfm, _ = frontmatter(p)
        inv = [i for i in split_list(fm_field(nfm, "invalidations")) if not i.lower().startswith("resolved")]
        if inv or split_list(fm_field(nfm, "catalysts")):
            kill += inv
            cats += split_list(fm_field(nfm, "catalysts"))
            note_used = note_used or os.path.basename(p)
        if len(kill) >= 3:
            break

    bands = [("kmp", "\n".join(kp_bullets), 3), ("notes", node_notes + " " + sector, 2),
             ("kill", " ; ".join(kill + cats), 1)]
    gate_text = sector + " " + r.get("node_themes", "") + " " + theme_membership + " " + node_notes

    scores = collections.Counter()
    hits = {}
    for d, pat in PATTERNS.items():
        gate = GATE.get(d)
        if gate and not re.search(gate, gate_text, re.I):
            continue
        for band, text, w in bands:
            m = re.search(pat, text, re.I)
            if m:
                scores[d] += w
                hits.setdefault(d, (band, m.group(0), w))
                break
    driver, why = "UNKNOWN", "no pattern hit any evidence band"
    if scores:
        top = scores.most_common()
        best, best_score = top[0]
        tier = {3: 0, 2: 1, 1: 2}
        if len(top) > 1 and top[1][1] == best_score:
            # tie: prefer the candidate whose hit landed in the strongest evidence band
            tied = [d for d, s in top if s == best_score]
            best = sorted(tied, key=lambda d: tier.get(hits[d][2], 9))[0]
            why = "tie at score %d between %s - resolved by evidence band" % (best_score, "/".join(tied))
        driver = best
    if driver == "UNKNOWN" and kp_bullets == []:
        for th in [t.strip() for t in theme_membership.split(";")]:
            if th in THEME_FALLBACK:
                driver, why = THEME_FALLBACK[th], "theme fallback (node has no Key moving pieces)"
                break
    if tk in OVERRIDES:
        driver = OVERRIDES[tk][0]
        why = "override: " + OVERRIDES[tk][1]

    ev = ""
    band, term, w = hits.get(driver, ("", "", 0))
    for b in kp_bullets:
        if term and re.search(re.escape(term), b, re.I):
            ev = b
            break
    if not ev and kp_bullets:
        ev = kp_bullets[0]
    if not ev:
        ev = node_notes or "(no causal text in the vault)"

    # --- how strong is the evidence for THIS assignment, and what is it based on? ---
    pat = PATTERNS.get(driver, "")
    kill_hit = bool(pat and pat != "" and re.search(pat, " ; ".join(kill + cats), re.I))
    kmp_hit = bool(pat and pat != "" and re.search(pat, "\n".join(kp_bullets), re.I))
    notes_hit = bool(pat and pat != "" and re.search(pat, node_notes + " " + sector, re.I))
    if kill_hit:
        strength, basis = "killswitch", "vault"
    elif kmp_hit:
        strength, basis = "key-moving-pieces", "vault"
    elif notes_hit:
        strength, basis = "node-notes", "vault"
    else:
        strength, basis = "sector/theme only", "analyst"
    if tk in OVERRIDES and basis == "analyst":
        basis = "analyst (override)"

    rows.append({
        "ticker": tk, "company": r["company"], "in_book": r["in_book"], "sector": sector,
        "theme_membership": theme_membership, "driver": driver,
        "parent_driver": DRIVERS[driver][4], "driver_variable": DRIVERS[driver][0],
        "mechanism": DRIVERS[driver][1], "sign": DRIVERS[driver][2], "lag": DRIVERS[driver][3],
        "evidence_strength": strength, "basis": basis,
        "evidence_band": band, "matched_term": term,
        "evidence": ev[:350], "killswitch": (kill[0] if kill else "")[:250],
        "evidence_note": note_used, "assignment_reason": why,
        "all_hits": "/".join("%s:%d" % (d, s) for d, s in scores.most_common(4)),
    })

with open("/tmp/driverwork/drivers.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

by = collections.defaultdict(list)
for r in rows:
    by[r["driver"]].append(r["ticker"])
print("ROSTER %d names -> %d drivers\n" % (len(rows), len([d for d in by if d != "UNKNOWN"])))
for d in DRIVERS:
    if d in by:
        print("%-15s %-44s %3d  %s" % (d, DRIVERS[d][0][:42], len(by[d]), ",".join(sorted(by[d]))))
print("\nby parent driver (the exogenous variable):")
par = collections.defaultdict(list)
for r in rows:
    par[r["parent_driver"]].append(r["ticker"])
for p, ts in sorted(par.items(), key=lambda kv: -len(kv[1])):
    print("  %-18s %3d  %s" % (p, len(ts), ",".join(sorted(ts)[:18])))
print("\nunclassified: %s" % (",".join(sorted(by.get("UNKNOWN", []))) or "none"))
print("written: /tmp/driverwork/drivers.csv")
