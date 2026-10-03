#!/usr/bin/env python3
"""kg_repair5.py — wire remaining evidence gaps from existing Claims nodes."""
import os, re, glob

VAULT = "/documents/Finance Knowledge Graph"
NOTES = os.path.join(VAULT, "Notes")
CL = os.path.join(VAULT, "Claims")

def fm_split(txt):
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        return (parts[1], parts[2]) if len(parts) >= 3 else (parts[1], "")
    return None, txt

def links_in(text):
    return set(re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text))

# claim titles by ticker-name match
claim_files = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(os.path.join(CL, "*.md"))}
claims_by_tk = {}
for title, p in claim_files.items():
    txt = open(p, encoding="utf-8").read()
    fm, _ = fm_split(txt)
    m = re.search(r'^company:\s*\[\[([^\]]+)\]\]|^company:\s*"([^"]+)"', fm or "", re.M)
    c = (m.group(1) or m.group(2)) if m else ""
    claims_by_tk.setdefault(c.lower(), []).append(title)

BEAR = "AI capex off-balance-sheet debt financed"
BULL = ["AI demand remains supply-constrained", "AI server growth sustainable"]

# MTSI, SMTC, SNDK, Groundbreaking
plan = {
    "2026-08-19 MTSI research.md": ("[[MTSI Q4 FY26 revenue guide]]", BEAR),
    "2026-08-19 SMTC research.md": ("[[SMTC Q3 FY27 revenue guide]]", BEAR),
    "2026-08-19 SNDK research.md": ("[[SNDK FQ1 2027 revenue guide]]", BEAR),
    "2026-08-21 Groundbreaking Medical Devices research.md": ("[[Moderna intismeran melanoma interim]]", "[[2026-08-20 Biotech alpha scan]]"),
}

def set_field(fm, key, toks):
    val = ", ".join(f'"{t}"' for t in toks)
    line = f"{key}: [{val}]"
    m = re.search(rf"^{key}:.*(\n|$)", fm, re.M)
    return fm[:m.start()] + line + "\n" + fm[m.end():] if m else fm.rstrip() + "\n" + line + "\n"

done = 0
for name, (f_toks, a_toks) in plan.items():
    p = os.path.join(NOTES, name)
    if not os.path.exists(p):
        print("MISSING note:", name)
        continue
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None:
        continue
    f_links = links_in(f_toks) or {f_toks}
    a_links = links_in(a_toks) if isinstance(a_toks, str) else set(a_toks)
    for ex in (a_toks,) if isinstance(a_toks, str) else tuple():
        a_links |= links_in(ex)
    nfm = set_field(fm, "evidence_for", sorted(f_links))
    nfm = set_field(nfm, "evidence_against", sorted(a_links))
    open(p, "w", encoding="utf-8").write("---" + nfm + "---" + body)
    done += 1
    print(f"wired: {name}")
print(f"done: {done}")