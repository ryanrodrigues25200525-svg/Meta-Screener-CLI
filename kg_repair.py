#!/usr/bin/env python3
"""kg_repair.py — deterministic integrity fixes for the Finance KG.

1. Move recovery_*.md -> .archive/ (git mv, Obsidian ignores dotfolders)
2. Add missing closing '---' to notes missing it (SMCI, MRNA)
3. Wrap 8 legacy TRADINGAGENTS opinion notes with minimal frontmatter
4. Normalize nested-bracket arrays in Themes frontmatter (74 files)
5. Fix README [[Theme: X]] link; add scheduled:true to future-dated notes
6. Add generated:true markers to Graph-Index.md / Portfolio.md
7. Convert prose fundamentals -> structured numeric fields on Companies
8. Add note_type to notes by content/idea_source (signal|scan|thesis)
9. Create company nodes for deal parties (onsemi ON, Synaptics SYNA, Schneider, Cognite)
"""
import os, re, glob, subprocess, datetime

VAULT = "/documents/Finance Knowledge Graph"
TODAY = datetime.date.today().isoformat()

def fm_split(txt):
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        return (parts[1], parts[2]) if len(parts) >= 3 else (parts[1], "")
    return None, txt

def links_in(text):
    return set(re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text))

def in_fm(path, key):
    txt = open(path, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None:
        return None, txt, fm, body
    m = re.search(rf"^{re.escape(key)}:", fm, re.M)
    return (m is not None), txt, fm, body

# 1. recovery files -> .archive
arc = os.path.join(VAULT, ".archive")
os.makedirs(arc, exist_ok=True)
moved = 0
for f in glob.glob(os.path.join(VAULT, "recovery_*.md")):
    dst = os.path.join(arc, os.path.basename(f))
    subprocess.run(["git", "-C", VAULT, "mv", f, dst], capture_output=True)
    moved += 1
print(f"1) recovery files moved: {moved}")

# 2. missing closing ---
for rel, name in [("Notes/2026-08-18 Super Micro SMCI research.md", "SMCI"),
                  ("Notes/2026-08-19 Moderna MRNA research.md", "MRNA")]:
    p = os.path.join(VAULT, rel)
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm and body and not body.startswith("\n---") and "---" not in body.split("\n")[0][:4]:
        lines = txt.split("\n")
        # insert '---' before first body heading line
        for i, ln in enumerate(lines):
            if ln.startswith("# "):
                lines.insert(i, "---")
                break
        open(p, "w", encoding="utf-8").write("\n".join(lines))
        print(f"2) fixed closing ---: {name}")

# 3. wrap opinion notes
opinion_notes = glob.glob(os.path.join(VAULT, "Notes", "2026-08-21 TRADINGAGENTS * opinion.md"))
for p in opinion_notes:
    base = os.path.basename(p)
    ticker = re.search(r"TRADINGAGENTS (\w+) opinion", base).group(1)
    txt = open(p, encoding="utf-8").read()
    if txt.startswith("---"):
        continue
    m = re.search(r"^\s*(Overweight|Underweight|Neutral|Hold|Buy|Sell)\b", txt, re.M)
    dec = (m.group(1) if m else "").upper()
    comp = ""
    idx = {t.lower(): t for t in [os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(VAULT, "Companies", "*.md"))]}
    for f in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        c = open(f, encoding="utf-8").read()
        mm = re.search(rf"^ticker:\s*[\"']?{ticker}[\"']?", c, re.M)
        if mm:
            comp = os.path.splitext(os.path.basename(f))[0]
            break
    fm = ("---\n" + 'type: "research-note"\ndate: "2026-08-21"\n'
          f'topic: "{ticker} TradingAgents opinion (signal)"\n'
          + (f'companies: ["[[{comp}]]"]\n' if comp else "companies: []\n")
          + 'note_type: "signal"\nidea_source: "AI-routed"\n'
          + (f'decision: "{dec}"\n' if dec else "")
          + 'model_source: "tradingagents (openrouter free)"\nstatus: "open"\nimportance: 2\n---\n\n')
    open(p, "w", encoding="utf-8").write(fm + txt)
    print(f"3) wrapped opinion: {ticker} {dec}")

# 4. theme nested-array normalization
fixed = 0
for p in glob.glob(os.path.join(VAULT, "Themes", "*.md")):
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None or "[[[" not in fm:
        continue
    changed = False
    for key in ("companies", "research", "sources", "themes"):
        m = re.search(rf"^{key}:[^\n]*(\n[ \t]*- [^\n]*)*", fm, re.M)
        if not m:
            continue
        seg = m.group(0)
        if "[[[" not in seg:
            continue
        toks = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", seg)
        uniq = list(dict.fromkeys(t.strip() for t in toks))
        if uniq:
            new = key + ": [" + ", ".join(f'"[[{t}]]"' for t in uniq) + "]"
            fm = fm[:m.start()] + new + fm[m.end():]
            changed = True
    if changed:
        open(p, "w", encoding="utf-8").write("---" + fm + "---" + body)
        fixed += 1
print(f"4) theme arrays normalized: {fixed}")

# 5. README link + scheduled flags
rp = os.path.join(VAULT, "README.md")
rt = open(rp, encoding="utf-8").read()
nt = rt.replace("[[Theme: AI infrastructure]]", "[[AI infrastructure]]")
if nt != rt:
    open(rp, "w", encoding="utf-8").write(nt)
    print("5) README link fixed")
for f in ["Notes/2026-09-01 Frontier.md", "Notes/2026-09-01 Market Dashboard.md"]:
    p = os.path.join(VAULT, f)
    if os.path.exists(p):
        t = open(p, encoding="utf-8").read()
        fm, body = fm_split(t)
        if fm is not None and "scheduled: true" not in fm:
            fm2 = fm.rstrip() + "\nscheduled: true\n"
            open(p, "w", encoding="utf-8").write("---" + fm2 + "---" + body)
            print(f"5) scheduled flag: {f}")

# 6. generated markers
for rel in ("Graph-Index.md", "Portfolio.md"):
    p = os.path.join(VAULT, rel)
    if not os.path.exists(p):
        continue
    t = open(p, encoding="utf-8").read()
    fm, body = fm_split(t)
    if fm is None:
        t2 = "---\ntype: \"dashboard\"\ngenerated: true\n---\n\n" + t
        open(p, "w", encoding="utf-8").write(t2)
    elif "generated: true" not in fm:
        fm2 = fm.rstrip() + "\ngenerated: true\n"
        open(p, "w", encoding="utf-8").write("---" + fm2 + "---" + body)
    print(f"6) generated marker: {rel}")

# 7. fundamentals -> structured
converted = 0
for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None:
        continue
    m = re.search(r'^fundamentals:\s*"([^"]*)"', fm, re.M)
    if not m:
        continue
    s = m.group(1)
    def num(v):
        v = v.replace(",", "")
        mul = 1
        if v.endswith("T"): mul, v = 1e12, v[:-1]
        elif v.endswith("B"): mul, v = 1e9, v[:-1]
        elif v.endswith("M"): mul, v = 1e6, v[:-1]
        try: return float(v) * mul
        except Exception: return None
    fields = {}
    rm = re.search(r"rev \$?([0-9.]+[BT]?)", s)
    if rm: fields["revenue_usd"] = num(rm.group(1))
    pm = re.search(r"fwdPE\s*([0-9.]+)", s)
    if pm: fields["forward_pe"] = float(pm.group(1))
    cm = re.search(r"mktcap \$?([0-9.]+[BT]?)", s)
    if cm: fields["market_cap_usd"] = num(cm.group(1))
    if not fields:
        continue
    add = "\n".join(f"{k}: {v}" for k, v in fields.items())
    fm2 = re.sub(r'^fundamentals:\s*"[^"]*"\n?', "", fm, flags=re.M)
    fm2 = fm2.rstrip() + f'\nfundamentals_basis: "yfinance spot {TODAY}"\n' + add + "\n"
    open(p, "w", encoding="utf-8").write("---" + fm2 + "---" + body)
    converted += 1
print(f"7) fundamentals structured: {converted}")

# 8. note_type categorization
def classify(base, ide):
    nm = base.lower()
    if any(k in nm for k in ("tradingagents", "signals", "twitter claims", "opinion")):
        return "signal"
    if any(k in nm for k in ("meta-screen", "analyst consensus", "catalysts", "frontier",
                             "positions monitor", "reason", "econ-calendar", "market-sentiment",
                             "sector-rotation", "volatility-regime", "unusual-options",
                             "market dashboard", "theme baskets", "catalyst grades", "13f",
                             "podcast", "alpha scan", "book thesis-review")):
        return "scan"
    if any(k in (ide or "") for k in ("sentiment", "twitter", "podcast", "alpha-scan",
                                       "screen", "13f")):
        return "signal" if ide not in ("portfolio (IBKR paper)", "portfolio (PM)") else "thesis"
    if any(k in nm for k in ("research", "earnings")):
        return "thesis"
    return None

ct = {"signal": 0, "scan": 0, "thesis": 0}
for p in glob.glob(os.path.join(VAULT, "Notes", "*.md")):
    txt = open(p, encoding="utf-8").read()
    fm, body = fm_split(txt)
    if fm is None:
        continue
    if re.search(r"^note_type:", fm, re.M):
        continue
    ide = None
    mi = re.search(r"^idea_source:\s*[\"']?([^\"'\n]+)", fm, re.M)
    if mi: ide = mi.group(1).strip()
    nt = classify(os.path.basename(p), ide)
    if nt:
        fm2 = fm.rstrip() + f"\nnote_type: \"{nt}\"\n"
        open(p, "w", encoding="utf-8").write("---" + fm2 + "---" + body)
        ct[nt] += 1
print(f"8) note_type added: signal {ct['signal']} / scan {ct['scan']} / thesis {ct['thesis']}")

# 9. deal-party company nodes
parties = {"onsemi": ("ON", "onsemi (formerly ON Semiconductor)", "Semiconductors"),
           "Synaptics": ("SYNA", "Synaptics", "Semiconductors"),
           "Schneider Electric": (None, "Schneider Electric", "Industrial / Electrification"),
           "Cognite": (None, "Cognite", "Industrial AI software")}
created = 0
for name, (tk, full, sector) in parties.items():
    p = os.path.join(VAULT, "Companies", full + ".md")
    if os.path.exists(p):
        continue
    body = ("---\n" + 'type: "company"\n'
            + (f'ticker: "{tk}"\n' if tk else 'ticker: ""\n')
            + f'name: "{full}"\nsector: "{sector}"\nthemes: []\ncompetitors: []\npartners: []\n'
            + 'position_trend: ""\nresearch: []\nsources: []\n'
            + 'notes: "Created 2026-08-31 from deal-party wiring (kg_repair)."\n---\n\n'
            + f"# {full}\n\n## Business\n<!-- stub -->\n\n")
    open(p, "w", encoding="utf-8").write(body)
    created += 1
print(f"9) deal-party nodes created: {created}")
print("DONE")