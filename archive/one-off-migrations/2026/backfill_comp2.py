#!/usr/bin/env python3
"""Backfill competitor/partner/position fields onto the REMAINING company nodes
(shortlist + watchlist names not covered by the holdings backfill). Grounded in
their sector/theses. Idempotent, skips nodes that already have the fields."""
import os, re, glob

KG_COMPANIES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Companies")

# ticker-independent: map by company-node FILENAME -> (competitors, partners, position)
BACKFILL = {
    "NVIDIA": ("[AMD, Broadcom, Intel] (AI GPUs/accelerators)",
               "[TSMC — fab UPSIDE; hyperscalers (MSFT/Meta/GOOG) — demand RISK]", "gaining"),
    "AMD": ("[NVIDIA, Intel] (GPUs/CPUs)",
            "[TSMC — fab; data-center hyperscalers — demand]", "gaining"),
    "Broadcom": ("[NVIDIA, Marvell, Cisco] (AI networking/ASICs)",
                 "[TSMC — fab; VMware — software; hyperscaler ASIC deals — demand]", "gaining"),
    "Micron Technology": ("[Samsung, SK Hynix] (DRAM/NAND/HBM)",
                          "[HBM supply to NVIDIA/hyperscalers — UPSIDE; memory-price cycle — RISK]", "gaining"),
    "SanDisk Corporation": ("[Western Digital, Kioxia, Micron] (NAND/storage)",
                            "[NAND supply chain; consumer + data-center demand]", "stable"),
    "Super Micro Computer": ("[Dell, HPE, Lenovo] (AI servers)",
                             "[NVIDIA — GPU supply UPSIDE; hyperscaler AI-infra buildout — demand]", "gaining"),
    "SoFi Technologies": ("[Chime, Robinhood, LendingClub, Marcus (GS)] (fintech/neobank)",
                          "[Bank-license platform — UPSIDE; student-loan + credit — rate RISK]", "gaining"),
    "Nuvation Bio": ("[Kura Oncology, Mirati/BMS, Dizal] (precision oncology)",
                     "[JPM-initiated — institutional UPSIDE; clinical/pipeline — binary RISK]", "stable"),
    "Capricor Therapeutics": ("[Bristol Myers, Mesoblast, HeartBio] (cell therapy)",
                              "[PDUFA catalyst — event-driven UPSIDE; FDA — approval RISK]", "stable"),
    "Moderna": ("[Pfizer/BioNTech, Novavax] (mRNA)",
                "[mRNA platform — pipeline UPSIDE; COVID-demand collapse — RISK]", "losing"),
    "Ford Motor": ("[GM, Toyota, Stellantis, Tesla] (OEM)",
                   "[EV transition — capex RISK; F-150 franchise — cash UPSIDE]", "stable"),
    "Verizon": ("[AT&T, T-Mobile, Comcast] (US telecom)",
                "[Spectrum/5G — capex RISK; millimeter/dividend — income UPSIDE]", "stable"),
    "ConocoPhillips": ("[Exxon, Chevron, Occidental, EOG] (upstream)",
                       "[Permian/Alaska/international — cost structure; crude price — RISK]", "stable"),
    "Chevron": ("[Exxon, Shell, BP, ConocoPhillips] (integrated)",
                "[OPEC — supply; Permian — cost floor UPSIDE]", "stable"),
    "Marathon Petroleum": ("[Valero, Phillips 66, HF Sinclair] (refiners)",
                           "[Crack spreads — margin RISK; MPLX midstream — UPSIDE]", "stable"),
    "Valero Energy": ("[Marathon Petroleum, Phillips 66, HF Sinclair] (refiners)",
                      "[Crack spread/RVO — margin; renewable diesel — UPSIDE]", "stable"),
    "RTX": ("[Boeing Defense, Lockheed, Northrop] (defense/aero)",
            "[GOVT defense budgets — UPSIDE; Pratt GTF engine — quality RISK]", "stable"),
    "Lockheed Martin": ("[RTX/Northrop Grumman/Boeing Def] (defense primes)",
                        "[F-35 — franchise UPSIDE; govt spending cycle — RISK]", "stable"),
    "Aehr Test Systems": ("[Advantest, Teradyne, Cohu] (semiconductor test)",
                          "[SiC/GaN test demand — UPSIDE; customer concentration — RISK]", "gaining"),
    "Applied Optoelectronics": ("[Coherent, Lumentum, Source Photonics] (optical transceivers)",
                                "[AI data-center 800G/1.6T — UPSIDE; single-customer — RISK]", "gaining"),
    "AXT Inc": ("[Sumitomo, Shin-Etsu] (compound-semiconductor substrates)",
                "[GaAs/InP substrates for AI/optical — UPSIDE; China exposure — RISK]", "stable"),
    "Lumentum Holdings": ("[Coherent, II-VI, source] (optical components)",
                          "[Hyperscaler optical — UPSIDE; telecom capex — RISK]", "gaining"),
    "MACOM Technology Solutions": ("[Analog Devices, Broadcom, Qorvo] (RF/analog)",
                                   "[AI networking/optical — UPSIDE; defense — semi-downturn RISK]", "gaining"),
    "MaxLinear": ("[Broadcom, Marvell, Silicon Labs] (mixed-signal)",
                  "[AI/optical PAM4 — UPSIDE; inventory correction — RISK]", "gaining"),
    "Semtech Corp": ("[ADI, TI, Broadcom] (analog/semis)",
                     "[Sierra Wireless/IoT — UPSIDE; tower/high-growth debt — RISK]", "stable"),
    "Nebius Group": ("[CoreWeave, Lambda, Oracle Cloud] (AI cloud)",
                     "[NVIDIA HPC/AI-cloud demand — UPSIDE; capex/competition — RISK]", "gaining"),
    "POET Technologies": ("[Coherent, Lumentum, Intel optical] (photonic interposers)",
                          "[AI optical modules — UPSIDE; early-stage — binary RISK]", "stable"),
    "EWJ": ("[VWO, EEM, DXJ] (Japan equity ETFs)",
            "[Japan corporate-governance reform — UPSIDE; yen/rate — FX RISK]", "stable"),
    "AVUV": ("[AVDV, DFSV, VBR] (US small-cap value factor)",
             "[Value-factor regime — tailwind; small-cap — liquidity RISK]", "gaining"),
}

for name, (comps, parts, pos) in BACKFILL.items():
    p = os.path.join(KG_COMPANIES, f"{name}.md")
    if not os.path.exists(p):
        print(f"  ! no node: {name}")
        continue
    txt = open(p, encoding="utf-8").read()
    orig = txt
    if re.search(r"^competitors:", txt, re.M):
        print(f"  - skip (already has fields): {name}")
        continue
    # insert fields after 'sector:' (or 'type:')
    anchor = "sector:"
    if not re.search(rf"^{anchor}.*$", txt, re.M):
        anchor = "type:"
    txt = re.sub(rf"^({anchor}.*)$", f"\\1\ncompetitors: \"{comps}\"\npartners: \"{parts}\"\nposition_trend: \"{pos}\"",
                 txt, count=1, flags=re.M)
    if "## Competitors" not in txt:
        txt += f"\n## Competitors\n{comps}\n"
    if "## Partners & ecosystem" not in txt:
        txt += f"\n## Partners & ecosystem\n{parts}\n"
    open(p, "w", encoding="utf-8").write(txt)
    print(f"  ✓ {name}")
