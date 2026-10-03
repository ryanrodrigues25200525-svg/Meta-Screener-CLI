#!/usr/bin/env python3
"""Backfill competitor/partner/position fields onto the company nodes for all
current PM holdings, using the TradingAgents verdict + thesis data already in
the notes. Adds frontmatter fields + a 'Competitors' and 'Partners & ecosystem'
section if missing. Idempotent."""
import os, re, glob

KG_COMPANIES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Companies")

# sector-appropriate competitors + partners per holding (grounded in the
# research notes / sector frameworks, honest about both risk & upside)
BACKFILL = {
    "Petrobras": dict(
        competitors="[Exxon Mobil, Shell, Chevron, PetroChina] (integrated majors)",
        partners="[Brazilian gov't as controlling shareholder — RISK: dividend-policy/fiscal interference; pre-salt JVs — UPSIDE]",
        position="stable", notes_note="Cheapest integrated major; dividend coverage ~6x"),
    "Viatris": dict(
        competitors="[Teva, Amneal, Sandoz/Novartis, Perrigo] (generic pharma)",
        partners="[Mylan heritage net (legacy scale) — inverse; Upjohn divestiture — cleansed book]",
        position="stable"),
    "General Motors": dict(
        competitors="[Ford, Toyota, Stellantis, Tesla, BYD] (OEMs)",
        partners="[EVgo — EV-charging UPSIDE; SAIC-GM JV — China exposure RISK; GM Financial — self-liquidating debt]",
        position="stable"),
    "SM Energy": dict(
        competitors="[Diamondback, Permian Resources, Matador, Devon] (Permian E&P)",
        partners="[Crude/crack-price linkage — commodity RISK; Permian midstream takeaway — UPSIDE]",
        position="stable"),
    "Vale": dict(
        competitors="[BHP, Rio Tinto, Fortescue] (miners)",
        partners="[Carajás low-cost mine — cost floor UPSIDE; Brazil gov't — policy RISK]",
        position="stable"),
    "Prudential Financial": dict(
        competitors="[MetLife, AIG, Lincoln, Principal] (insurers)",
        partners="[Hedging counterparties — rate RISK; Japan operations — structural drag RISK]",
        position="stable"),
    "Conagra Brands": dict(
        competitors="[General Mills, Kraft Heinz, Campbell's, Hormel] (packaged food)",
        partners="[Retailer relationships (Walmart etc.) — customer-concentration RISK]",
        position="stable"),
    "Pfizer": dict(
        competitors="[Merck, BMS, J&J, Eli Lilly, AbbVie] (big pharma)",
        partners="[BioNTech (mRNA), GLP-1 partnerships — pipeline UPSIDE; patent-cliff competitors]",
        position="stable"),
    "Novo Nordisk": dict(
        competitors="[Eli Lilly (oral GLP-1 — gaining), Sanofi, Merck]",
        partners="[GLP-1 supply network — UPSIDE; pandemic-adjacent demand — RISK]",
        position="losing"),  # TA flagged share-loss to Lilly's oral GLP-1
    "HP Inc": dict(
        competitors="[Dell, Lenovo, Apple, Acer] (PC)",
        partners="[Intel/AMD — component RISK; enterprise/AI-PC refresh cycle — UPSIDE]",
        position="stable"),
    "Adobe": dict(
        competitors="[Salesforce (Experience Cloud — DB), Figma, Canva, Microsoft Copilot]",
        partners="[AWS/cloud infra — UPSIDE; SMB segment — demand RISK]",
        position="losing"),  # TA flagged Experience Cloud share loss + SMB softness
}

for name, data in BACKFILL.items():
    p = os.path.join(KG_COMPANIES, f"{name}.md")
    if not os.path.exists(p):
        print(f"  ! no node: {name}")
        continue
    txt = open(p, encoding="utf-8").read()
    orig = txt
    # add/refresh frontmatter fields
    for field, val in [("competitors", data["competitors"]),
                       ("partners", data["partners"]),
                       ("position_trend", data["position"])]:
        if re.search(rf"^{field}:", txt, re.M):
            txt = re.sub(rf"^{field}:.*$", f'{field}: "{val}"', txt, count=1, flags=re.M)
        else:
            # insert after 'sector:' line
            txt = re.sub(r"^(sector:.*)$", rf"\1\n{field}: \"{val}\"", txt, count=1, flags=re.M)
    # add 'Competitors' + 'Partners' sections if absent
    if "## Competitors" not in txt:
        txt += f"\n## Competitors\n{data['competitors']}\n"
    if "## Partners & ecosystem" not in txt:
        txt += f"\n## Partners & ecosystem\n{data['partners']}\n"
    open(p, "w", encoding="utf-8").write(txt)
    print(f"  ✓ {name}: changed={txt != orig}")
