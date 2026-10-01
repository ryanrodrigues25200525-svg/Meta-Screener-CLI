#!/usr/bin/env python3
"""fix_wrapped_links.py — repair wikilinks broken across a newline, and report unresolved links.

A `[[link]]` that wraps in the editor does not resolve in Obsidian and silently inflates the unresolved
count that kg_validate.py reports. Run this before every commit:

    python3 ~/Documents/finance-ai/fix_wrapped_links.py [--check-only]
"""
import argparse, glob, os, re, sys


def vault():
    for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
              os.path.expanduser("~/Documents/Finance Knowledge Graph")):
        if c and os.path.isdir(c):
            return c
    raise SystemExit("vault not found")


V = vault()
WRAP = re.compile(r"\[\[([^\]\n]*)\n\s*([^\]\n]*)\]\]", re.S)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    fixed = []
    for p in glob.glob(f"{V}/**/*.md", recursive=True):
        if "/.git/" in p:
            continue
        t = open(p, encoding="utf-8", errors="ignore").read()
        new = WRAP.sub(lambda m: f"[[{m.group(1).strip()} {m.group(2).strip()}]]", t)
        if new != t:
            fixed.append(os.path.relpath(p, V))
            if not a.check_only:
                open(p, "w", encoding="utf-8").write(new)
    print(f"wrapped wikilinks {'found' if a.check_only else 'repaired'}: {len(fixed)}")
    for f in fixed:
        print("  ", f)

    stems = {os.path.basename(x)[:-3] for x in glob.glob(f"{V}/**/*.md", recursive=True)}
    alias = set()
    for p in glob.glob(f"{V}/Companies/*.md") + glob.glob(f"{V}/Themes/*.md") + glob.glob(f"{V}/Sources/*.md"):
        fm = open(p, encoding="utf-8", errors="ignore").read().split("---", 2)[1]
        for grp in re.findall(r"aliases:\s*\[(.*?)\]", fm):
            alias |= {x.strip().strip('"\'') for x in grp.split(",")}
    known = stems | alias
    bad = 0
    for p in glob.glob(f"{V}/Notes/2026-09-1*.md") + glob.glob(f"{V}/Themes/*.md"):
        for link in re.findall(r"\[\[([^\]|#]+)", open(p, encoding="utf-8", errors="ignore").read()):
            if link not in known:
                bad += 1
                print(f"  UNRESOLVED {os.path.relpath(p, V)} -> {link[:60]}")
    print(f"unresolved links in recent notes/themes: {bad}")
    sys.exit(1 if fixed and a.check_only else 0)
