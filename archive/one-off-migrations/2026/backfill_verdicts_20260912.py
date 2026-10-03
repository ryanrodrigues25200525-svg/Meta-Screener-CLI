#!/usr/bin/env python3
"""PM Decision 2026-09-12 — write layer-3 verdicts + close holding gaps.

Writes into the thesis-research notes + company nodes:
  verdict, verdict-date, invalidations (kill-switches), catalysts, review_date.
Kill-switches/catalysts sourced from pm_trader.HOLDINGS_INTEL (curated, graph-native).
"""
import os, re, glob, sys

KG = "/tmp/kh/Documents/Finance Knowledge Graph"
NOTES = os.path.join(KG, "Notes")
COMPANIES = os.path.join(KG, "Companies")
TODAY = "2026-09-12"
NEXT_REVIEW = "2026-09-19"  # next weekly Positions Monitor run

# ticker -> (thesis note filename, company filename)
THESIS = {
    "PBR":  ("2026-08-21 PBR TradingAgents research", "Petrobras"),
    "VTRS": ("2026-08-21 VTRS TradingAgents research", "Viatris"),
    "GM":   ("2026-08-20 General Motors GM research", "General Motors"),
    "SM":   ("2026-08-21 SM TradingAgents research", "SM Energy"),
    "VALE": ("2026-08-21 VALE TradingAgents research", "Vale"),
    "PRU":  ("2026-08-21 PRU TradingAgents research", "Prudential Financial"),
    "GIS":  ("2026-08-21 GIS TradingAgents research", "General Mills"),
    "CAG":  ("2026-08-21 CAG TradingAgents research", "Conagra Brands"),
    "PFE":  ("2026-08-21 PFE TradingAgents research", "Pfizer"),
    "NVO":  ("2026-08-21 NVO TradingAgents research", "Novo Nordisk"),
    "ADBE": ("2026-08-20 Adobe ADBE research", "Adobe"),
    "HPQ":  ("2026-08-21 HPQ TradingAgents research", "HP Inc"),
}

# verdicts + kill-switches + catalysts (HOLDINGS_INTEL-derived; ADBE carries the TA kill-switch)
DATA = {
    "PBR":  ("INTACT", ["if government dividend-policy change occurs", "if crude prices collapse"], ["9% yield + 4.8x fwd; Brazil fiscal discount"]),
    "VTRS": ("INTACT", ["if generic prices keep deflating >$1B/yr", "if dilution spikes"], ["Generic-pricing stabilization; 14% FCF yield cash return"]),
    "GM":   ("INTACT", None, ["Dec-2026 Silverado/Sierra refresh; EV loss narrowing toward 2027 breakeven"]),
    "SM":   ("INTACT", ["if crude/crack normalization compresses FCF", "if leverage rises"], ["16% FCF yield; Permian production + crude recovery"]),
    "VALE": ("INTACT", ["if iron-ore price collapses", "if Brazil policy interference hits operations"], ["22% FCF yield + 8.6% div; iron-ore cost floor at low-cost Carajas"]),
    "PRU":  ("INTACT", ["if a rate-cut cycle compresses spread income", "if hedging losses compress spread income"], ["higher-for-longer rate tailwind; 8.3x fwd + 4.6% yield"]),
    "GIS":  ("INTACT", ["if FCF yield <7%", "if earnings decline accelerates"], ["6% yield + 10% FCF; price/mix holds in cereal/snacks"]),
    "CAG":  ("INTACT", ["if negative margins persist", "if dividend is cut"], ["7.6% yield + FCF; margin recovery as input costs ease"]),
    "PFE":  ("INTACT", ["if patent cliff losses outpace pipeline builds"], ["6% yield + pipeline inflection; Mounjaro-type partnerships"]),
    "NVO":  ("INTACT", ["if competition (Eli Lilly) compresses pricing", "if margins slip"], ["GLP-1 demand durable; 18% FCF yield"]),
    "ADBE": ("WEAKENED", None, ["fwd ~10x + Firefly/AI monetization inflection; ~9% FCF yield"]),
    "HPQ":  ("INTACT", ["if PC demand stays weak", "if margin compression persists"], ["12.6% FCF yield + AI-PC refresh cycle"]),
}

# non-held threatened theses (Reason.md ⚠) — verdict only
EXTRA = {
    "2026-08-18 Small-cap value AVUV research": "WEAKENED",
    "2026-08-18 Super Micro SMCI research": "WEAKENED",
    "2026-08-18 NVIDIA research": "WEAKENED",
    "2026-08-18 AMD research": "WEAKENED",
}

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

def write(p, txt):
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)

def set_field(txt, field, value, append_if_missing=True):
    """Replace `field:` line; append before closing --- if absent."""
    pat = re.compile(r"^" + re.escape(field) + r":.*$", re.M)
    if pat.search(txt):
        return pat.sub(field + ": " + value, txt, count=1)
    if append_if_missing:
        # insert before the final closing ---
        idx = txt.rfind("\n---")
        if idx != -1:
            return txt[:idx] + "\n" + field + ": " + value + txt[idx:]
    return txt

def fmt_list(items):
    return '["' + '", "'.join(items) + '"]'

changed = []
for tk, (note_name, comp_name) in THESIS.items():
    verdict, kills, cats = DATA[tk]
    np_ = os.path.join(NOTES, note_name + ".md")
    if not os.path.exists(np_):
        print(f"!! missing thesis note {note_name}"); continue
    txt = read(np_)
    if kills is not None:
        txt = set_field(txt, "invalidations", fmt_list(kills))
    txt = set_field(txt, "catalysts", fmt_list(cats))
    txt = set_field(txt, "verdict", '"' + verdict + '"')
    txt = set_field(txt, "verdict-date", '"' + TODAY + '"')
    txt = set_field(txt, "review_date", '"' + NEXT_REVIEW + '"')
    txt = set_field(txt, "next_review", '"' + NEXT_REVIEW + '"')
    write(np_, txt)
    changed.append(f"  {tk}: thesis note {note_name} -> verdict {verdict}")
    # company node
    cp = os.path.join(COMPANIES, comp_name + ".md")
    if os.path.exists(cp):
        ct = read(cp)
        ct = set_field(ct, "verdict", '"' + verdict + '"')
        ct = set_field(ct, "verdict-date", '"' + TODAY + '"')
        write(cp, ct)
        changed.append(f"  {tk}: company node {comp_name} verdict {verdict}")

for note_name, verdict in EXTRA.items():
    np_ = os.path.join(NOTES, note_name + ".md")
    if not os.path.exists(np_):
        print(f"!! missing note {note_name}"); continue
    txt = read(np_)
    txt = set_field(txt, "verdict", '"' + verdict + '"')
    txt = set_field(txt, "verdict-date", '"' + TODAY + '"')
    write(np_, txt)
    changed.append(f"  {note_name} -> {verdict}")

print("\n".join(changed))
print(f"\n{len(changed)} writes done.")