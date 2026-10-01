#!/usr/bin/env python3
"""Repair: move verdict-date/review_date from note bodies into frontmatter (idempotent)."""
import os, re

KG = "/tmp/kh/Documents/Finance Knowledge Graph"
NOTES = os.path.join(KG, "Notes")
COMPANIES = os.path.join(KG, "Companies")
TODAY = "2026-09-12"
NEXT_REVIEW = "2026-09-19"

NOTE_FILES = [
    "2026-08-21 PBR TradingAgents research", "2026-08-21 VTRS TradingAgents research",
    "2026-08-20 General Motors GM research", "2026-08-21 SM TradingAgents research",
    "2026-08-21 VALE TradingAgents research", "2026-08-21 PRU TradingAgents research",
    "2026-08-21 GIS TradingAgents research", "2026-08-21 CAG TradingAgents research",
    "2026-08-21 PFE TradingAgents research", "2026-08-21 NVO TradingAgents research",
    "2026-08-20 Adobe ADBE research", "2026-08-21 HPQ TradingAgents research",
]
COMPANY_FILES = [
    "Petrobras", "Viatris", "General Motors", "SM Energy", "Vale",
    "Prudential Financial", "General Mills", "Conagra Brands", "Pfizer",
    "Novo Nordisk", "Adobe", "HP Inc",
]

FM_RE = re.compile(r"\A(---\s*\n.*?\n---\s*\n)", re.S)

def parse(txt):
    m = FM_RE.match(txt)
    if not m:
        return None, txt
    fm = m.group(1)
    body = txt[m.end():]
    return fm, body

def set_field(fm, field, value):
    pat = re.compile(r"^" + re.escape(field) + r":.*$", re.M)
    if pat.search(fm):
        return pat.sub(field + ": " + value, fm, count=1)
    # insert before closing ---
    idx = fm.rindex("\n---")
    return fm[:idx] + "\n" + field + ": " + value + fm[idx:]

def strip_body_fields(body):
    lines = body.split("\n")
    out = [ln for ln in lines if not re.match(r"^(verdict-date|review_date|next_review):", ln)]
    return "\n".join(out)

fixed = []
for name in NOTE_FILES:
    p = os.path.join(NOTES, name + ".md")
    txt = open(p, encoding="utf-8").read()
    fm, body = parse(txt)
    changed = False
    if fm is None:
        print(f"!! {name}: no frontmatter"); continue
    new_body = strip_body_fields(body)
    if new_body != body:
        changed = True
    fm2 = fm
    for f, v in (("verdict-date", '"' + TODAY + '"'), ("review_date", '"' + NEXT_REVIEW + '"')):
        old = fm2
        fm2 = set_field(fm2, f, v)
        if fm2 != old:
            changed = True
    if changed:
        open(p, "w", encoding="utf-8").write(fm2 + new_body)
        fixed.append("note " + name)

for name in COMPANY_FILES:
    p = os.path.join(COMPANIES, name + ".md")
    txt = open(p, encoding="utf-8").read()
    fm, body = parse(txt)
    if fm is None:
        print(f"!! {name}: no frontmatter"); continue
    changed = False
    new_body = strip_body_fields(body)
    if new_body != body:
        changed = True
    fm2 = fm
    for f, v in (("verdict", '"INTACT"'), ("verdict-date", '"' + TODAY + '"')):
        # company nodes: only ADBE is WEAKENED
        if name == "Adobe":
            v = '"WEAKENED"'
        old = fm2
        fm2 = set_field(fm2, f, v)
        if fm2 != old:
            changed = True
    if changed:
        open(p, "w", encoding="utf-8").write(fm2 + new_body)
        fixed.append("company " + name)

print("\n".join(fixed) if fixed else "nothing to fix")
print(f"{len(fixed)} files repaired")