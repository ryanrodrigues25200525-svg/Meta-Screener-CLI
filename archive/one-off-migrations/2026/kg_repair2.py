#!/usr/bin/env python3
"""kg_repair2.py — canonicalize theme company tokens to node titles + residual fixes."""
import os, re, glob

VAULT = "/documents/Finance Knowledge Graph"

def fm_split(txt):
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        return (parts[1], parts[2]) if len(parts) >= 3 else (parts[1], "")
    return None, txt

# ticker -> node title index
tick_idx = {}
for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
    txt = open(p, encoding="utf-8").read()
    fm, _ = fm_split(txt)
    if fm is None:
        continue
    m = re.search(r'^ticker:\s*["\']?([A-Za-z0-9.\-]+)["\']?', fm, re.M)
    if m and m.group(1):
        tick_idx[m.group(1).upper()] = os.path.splitext(os.path.basename(p))[0]

# 1. SMCI / MRNA closing ---
for rel in ["Notes/2026-08-18 Super Micro SMCI research.md",
            "Notes/2026-08-19 Moderna MRNA research.md"]:
    p = os.path.join(VAULT, rel)
    if not os.path.exists(p):
        continue
    txt = open(p, encoding="utf-8").read()
    if txt.startswith("---") and txt.count("---") < 3:
        lines = txt.split("\n")
        for i, ln in enumerate(lines):
            if ln.startswith("# ") and i > 1:
                lines.insert(i, "---")
                break
        open(p, "w", encoding="utf-8").write("\n".join(lines))
        print(f"closing --- added: {rel}")

# 2. canonicalize theme company tokens [[TICKER]] -> [[NodeTitle]] where resolvable
fixed = 0
for p in glob.glob(os.path.join(VAULT, "Themes", "*.md")):
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None:
        continue
    if "companies:" not in fm:
        continue
    def repl(mo):
        tok = mo.group(1).strip()
        up = tok.upper()
        if up in tick_idx:
            return f"[[{tick_idx[up]}]]"
        return mo.group(0)
    new_fm = re.sub(r"\[\[([^\]|]+)\]\]", repl, fm)
    if new_fm != fm:
        open(p, "w", encoding="utf-8").write("---" + new_fm + "---" + body)
        fixed += 1
print(f"theme company tokens canonicalized: {fixed}")

# 3. claims last_checked (from graded_on or date; empty otherwise -> leave)
done = 0
for p in glob.glob(os.path.join(VAULT, "Claims", "*.md")):
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None:
        continue
    if re.search(r"^last_checked:", fm, re.M):
        continue
    g = re.search(r'^graded_on:\s*["\']?([\d-]+)', fm, re.M)
    d = re.search(r'^date:\s*["\']?([\d-]+)', fm, re.M)
    val = g.group(1) if g else (d.group(1) if d else None)
    if val:
        fm2 = fm.rstrip() + f'\nlast_checked: "{val}"\n'
        open(p, "w", encoding="utf-8").write("---" + fm2 + "---" + body)
        done += 1
print(f"claims last_checked backfilled: {done}")
print("DONE")