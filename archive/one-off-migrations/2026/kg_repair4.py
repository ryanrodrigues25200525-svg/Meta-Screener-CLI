#!/usr/bin/env python3
"""kg_repair4.py — link-title fixes + missing Source nodes."""
import os, re, glob

VAULT = "/documents/Finance Knowledge Graph"

# 1. [[X/Twitter accounts]] -> [[X Twitter accounts]]
n = 0
for p in glob.glob(os.path.join(VAULT, "Notes", "*.md")):
    t = open(p, encoding="utf-8").read()
    n2 = t.replace("[[X/Twitter accounts]]", "[[X Twitter accounts]]")
    if n2 != t:
        open(p, "w", encoding="utf-8").write(n2)
        n += 1
print(f"X/Twitter link fixed in {n} files")

# 2. cnbc / stocktitan citations -> canonical source or plain text
n2 = 0
for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
    if ".archive" in p:
        continue
    t = open(p, encoding="utf-8").read()
    nxt = t.replace("[[cnbc.com]]", "[[CNBC]]")
    nxt = nxt.replace("[[cnbc.com 2026-08-04]]", "cnbc.com 2026-08-04")
    nxt = nxt.replace("[[stocktitan.net Q2 10-Q]]", "stocktitan.net Q2 10-Q")
    if nxt != t:
        open(p, "w", encoding="utf-8").write(nxt)
        n2 += 1
print(f"cnbc/stocktitan citations fixed in {n2} files")

# 3. missing Source nodes
for name, url in [("BioSpace", "https://www.biospace.com"),
                  ("stocktitan.net", "https://www.stocktitan.net")]:
    p = os.path.join(VAULT, "Sources", name + ".md")
    if not os.path.exists(p):
        body = ("---\n" + 'type: "source"\n'
                f'name: "{name}"\n'
                f'origin: "{url}"\n'
                'type_: "news/press"\n'
                'reliability: "medium"\n'
                'topic_areas: ["Health care","Press releases","SEC coverage"]\n'
                'notes: "Created 2026-08-31 (kg_repair4) for unresolved link cleanup."\n---\n\n'
                f"# {name}\n\nSource node. Origin: {url}\n")
        open(p, "w", encoding="utf-8").write(body)
        print(f"source node created: {name}")
print("DONE")