#!/usr/bin/env python3
"""build_roster.py - causal driver map, step 1: the roster.

Union of (a) the book (34 names from book_risk.py + pm_portfolio.json) and (b) every member of the
rotation / leading themes the vault tracks, resolved to tickers through the Companies nodes.
Writes /workspace/roster.csv and prints coverage so the causal pass knows exactly what it must cover.
"""
import csv, os, re, glob, json

KG = "/documents/Finance Knowledge Graph"
COMP = os.path.join(KG, "Companies")
THEMES = os.path.join(KG, "Themes")

BOOK = ["AAOI","AXTI","MU","SNDK","NBIS","POET","LITE","MTSI","SMTC","AEHR","MXL",
        "NVDA","TSM","AVGO","AMD","MRVL","WDC","ONTO","RMBS","TSEM","AEIS","SIMO",
        "GM","VTRS","VALE","CAG","GIS","HPQ","SM","PRU","NVO","PBR","PFE","ADBE"]

# the leading/rotation themes from the coverage + breadth notes, plus the book's own themes
ROTATION_THEMES = [
    "Software & SaaS", "Hyperscalers", "Cybersecurity", "Gold Miners", "Energy", "Oil & gas",
    "Copper Miners", "Materials", "Life Sciences Tools", "Exploration & Production", "Oil Services",
    "Information Technology", "Semis & Semicapital Equipment", "AI infrastructure", "Defense",
    "Financials", "Small-cap value", "Japan", "Utilities", "REITs",
]


def frontmatter(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    return (m.group(1) if m else ""), txt


def fm_list(fm, key):
    """Read 'key: [a, b]' or 'key:\n  - a\n  - b' into a python list of strings."""
    vals = []
    m = re.search(r"^%s:\s*(.*)$" % re.escape(key), fm, re.M)
    if not m:
        return vals
    inline = m.group(1).strip()
    if inline.startswith("["):
        vals.append(inline)
    else:
        # block list
        for line in fm.splitlines():
            if re.match(r"^\s+-\s+", line):
                vals.append(line.strip()[1:].strip())
    out = []
    for chunk in vals:
        for part in re.findall(r"\[\[([^\]]+)\]\]|\"([^\"]+)\"|'([^']+)'|([^,\[\]\s][^,\[\]]*)", chunk):
            v = next((x for x in part if x), "")
            v = v.strip().strip("'\"")
            # a quoted wikilink ("[[CRM]]") is matched by the quoted-string branch and keeps its
            # brackets - strip them (repeatedly, in case of doubled nesting) before use as a key
            for _ in range(3):
                if v.startswith("[[") and v.endswith("]]"):
                    v = v[2:-2].strip()
                elif v.startswith("[") and v.endswith("]"):
                    v = v[1:-1].strip()
                else:
                    break
            v = v.strip().strip("'\"")
            if v:
                out.append(v)
    return out


# --- index company nodes: title -> ticker, ticker -> title ---------------------
title2ticker, ticker2title, node_meta = {}, {}, {}
for p in glob.glob(os.path.join(COMP, "*.md")):
    title = os.path.basename(p)[:-3]
    fm, body = frontmatter(p)
    tk = re.search(r'^ticker:\s*"?([A-Za-z0-9\.\-]+)"?', fm, re.M)
    aliases = fm_list(fm, "aliases")
    sector = re.search(r'^sector:\s*(.*)$', fm, re.M)
    themes = fm_list(fm, "themes")
    notes = re.search(r'^notes:\s*(.*)$', fm, re.M)
    tk = tk.group(1) if tk else ""
    title2ticker[title] = tk or title
    if tk:
        ticker2title.setdefault(tk, title)
    node_meta[title] = {"ticker": tk, "sector": (sector.group(1).strip().strip('"') if sector else ""),
                        "themes": themes, "notes": (notes.group(1).strip().strip('"') if notes else ""),
                        "aliases": aliases, "path": p, "body": body}
    for a in aliases:
        title2ticker.setdefault(a, tk or title)

print("company nodes indexed: %d   (tickers: %d)" % (len(node_meta), len(ticker2title)))

# --- rotation theme members ---------------------------------------------------
theme_rows = []
missing_themes = []
for t in ROTATION_THEMES:
    p = os.path.join(THEMES, t + ".md")
    if not os.path.exists(p):
        missing_themes.append(t)
        continue
    fm, body = frontmatter(p)
    members = fm_list(fm, "companies")
    for m in members:
        tkr = title2ticker.get(m, "")
        title = ticker2title.get(tkr, m) if tkr else m
        theme_rows.append({"theme": t, "member": m, "ticker": tkr, "company_title": title})

print("rotation themes found: %d/%d   missing: %s" % (len(ROTATION_THEMES) - len(missing_themes),
                                                      len(ROTATION_THEMES), missing_themes or "none"))
print("theme member rows: %d" % len(theme_rows))
by_theme = {}
for r in theme_rows:
    by_theme.setdefault(r["theme"], []).append(r["ticker"] or ("?" + r["member"]))
for t in ROTATION_THEMES:
    if t in by_theme:
        print("  %-32s %2d members  %s" % (t, len(by_theme[t]), ",".join(by_theme[t][:14])))

unresolved = sorted({r["member"] for r in theme_rows if not r["ticker"]})
print("\nunresolved members (no company node / ticker): %d" % len(unresolved))
for u in unresolved[:40]:
    print("   ", u)

# --- union roster -------------------------------------------------------------
roster = {}
for t in BOOK:
    roster[t] = {"ticker": t, "in_book": 1, "themes": []}
for r in theme_rows:
    if not r["ticker"]:
        continue
    e = roster.setdefault(r["ticker"], {"ticker": r["ticker"], "in_book": 0, "themes": []})
    if r["theme"] not in e["themes"]:
        e["themes"].append(r["theme"])

rows = []
for t, e in sorted(roster.items()):
    md = node_meta.get(ticker2title.get(t, ""), {})
    s = md.get("sector", "")
    if s in ("", '""'):
        s = "MISSING"
    rows.append({"ticker": t, "company": ticker2title.get(t, t), "in_book": e["in_book"],
                 "sector": s, "theme_membership": "; ".join(e["themes"]),
                 "node_themes": "; ".join(md.get("themes", [])),
                 "node_notes": md.get("notes", "")[:200]})

with open("/workspace/roster.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print("\nROSTER: %d unique names  (%d book, %d rotation-only)"
      % (len(rows), sum(r["in_book"] for r in rows), sum(1 for r in rows if not r["in_book"])))
print("missing sector on roster names: %d" % sum(1 for r in rows if r["sector"] == "MISSING"))
print("written: /workspace/roster.csv")
