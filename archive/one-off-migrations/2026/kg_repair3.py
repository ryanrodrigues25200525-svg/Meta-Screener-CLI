#!/usr/bin/env python3
"""kg_repair3.py — collapse triple-bracket tokens + post-repair residual cleanup."""
import os, re, glob

VAULT = "/documents/Finance Knowledge Graph"

def fm_split(txt):
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        return (parts[1], parts[2]) if len(parts) >= 3 else (parts[1], "")
    return None, txt

# 1. collapse [[[ -> [[ in all frontmatter (Themes + anywhere else)
collapsed = 0
for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
    if ".archive" in p or p.endswith(("Graph-Index.md", "Portfolio.md", "KG-Health.md")):
        continue
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None or "[[[" not in fm:
        continue
    new_fm = fm.replace("[[[", "[[")
    open(p, "w", encoding="utf-8").write("---" + new_fm + "---" + body)
    collapsed += 1
print(f"triple-bracket collapsed: {collapsed}")

# 2. Welcome.md clean (remove obsidian 'create a link' artifact)
w = os.path.join(VAULT, "Welcome.md")
if os.path.exists(w):
    t = open(w, encoding="utf-8").read()
    t2 = t.replace("[[create a link]]", "[[Graph-Index]]")
    if t2 != t:
        open(w, "w", encoding="utf-8").write(t2)
        print("Welcome cleaned")

# 3. canonicalize any remaining ticker tokens in theme companies (after collapse)
tick_idx = {}
for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
    t = open(p, encoding="utf-8").read()
    fm, _ = fm_split(t)
    m = re.search(r'^ticker:\s*["\']?([A-Za-z0-9.\-]+)["\']?', fm or "", re.M)
    if m and m.group(1):
        tick_idx[m.group(1).upper()] = os.path.splitext(os.path.basename(p))[0]
fixed = 0
for p in glob.glob(os.path.join(VAULT, "Themes", "*.md")):
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None:
        continue
    def repl(mo):
        tok = mo.group(1).strip()
        return f"[[{tick_idx[tok.upper()]}]]" if tok.upper() in tick_idx else mo.group(0)
    new_fm = re.sub(r"\[\[([^\]|]+)\]\]", repl, fm)
    if new_fm != fm:
        open(p, "w", encoding="utf-8").write("---" + new_fm + "---" + body)
        fixed += 1
print(f"theme tokens canonicalized (round 2): {fixed}")
print("DONE")