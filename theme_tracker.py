#!/usr/bin/env python3
"""theme_tracker.py — actively track theme baskets in the Finance KG.

For every theme node with >=1 priced member:
  - computes equal-weight 1-month basket return from company price stamps
    (Companies/*.md frontmatter `price:` lines, written by price_stamp.py)
  - updates the theme node frontmatter: last_perf, last_updated (idempotent)
  - writes a dated snapshot note: Notes/<today> Theme Baskets.md

Self-contained: inserts its own deps path for yfinance (SPY benchmark).
Run: python3 /documents/finance-ai/theme_tracker.py
"""
import os, re, glob, sys, datetime

sys.path.insert(0, "/Users/ryanrodrigues/finance-ai/.ta-deps")
import yfinance as yf  # noqa: E402

VAULT = os.path.expanduser("~/Documents/Finance Knowledge Graph")
THEMES = os.path.join(VAULT, "Themes")
COMPANIES = os.path.join(VAULT, "Companies")
NOTES = os.path.join(VAULT, "Notes")

def fm_of(txt):
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        return (parts[1], parts[2]) if len(parts) >= 3 else (parts[1], "")
    return ("", txt)

def links_in(text):
    return set(re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text))

def upsert_fm(fm, lines):
    """append `lines` (list of 'key: value') to frontmatter if key absent (idempotent-ish:
    replaces existing value when the key exists)."""
    out = fm
    for ln in lines:
        key = ln.split(":", 1)[0].strip()
        m = re.search(rf"^{re.escape(key)}:[^\n]*(\n|$)", out, re.M)
        if m:
            out = out[:m.start()] + ln + "\n" + out[m.end():]
        else:
            out = out.rstrip("\n") + "\n" + ln + "\n"
    return out

# --- company stamps ---
tick, price = {}, {}
for p in glob.glob(os.path.join(COMPANIES, "*.md")):
    title = os.path.splitext(os.path.basename(p))[0]
    txt = open(p, encoding="utf-8").read()
    fm, _ = fm_of(txt)
    m = re.search(r"^ticker:\s*[\"']?([A-Za-z0-9.\-]+)", fm, re.M)
    tk = m.group(1).upper() if m and m.group(1) else None
    if tk:
        tick[title] = tk
    pm = re.search(r"^price:\s*\"[0-9.]+ \(([+-][0-9.]+)% 1m", fm, re.M)
    if pm and tk:
        price[tk] = float(pm.group(1))

# --- theme membership (both directions, corruption-tolerant) ---
theme_titles = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(THEMES, "*.md"))}
theme2tk = {t: set() for t in sorted(theme_titles)}
for tp in glob.glob(os.path.join(THEMES, "*.md")):
    name = os.path.splitext(os.path.basename(tp))[0]
    txt = open(tp, encoding="utf-8").read()
    for ref in links_in(txt):
        ref = ref.strip()
        if ref in tick:
            theme2tk[name].add(tick[ref])
for title, tk in tick.items():
    txt = open(os.path.join(COMPANIES, title + ".md"), encoding="utf-8").read()
    for ref in links_in(fm_of(txt)[0]) | links_in(txt):
        ref = ref.strip()
        if ref in theme_titles:
            theme2tk[ref].add(tk)

# --- SPY benchmark ---
spy_pct = None
try:
    spy = yf.Ticker("SPY").history(period="1mo")
    spy_pct = (float(spy["Close"].iloc[-1]) / float(spy["Close"].iloc[0]) - 1) * 100
except Exception as e:
    print("SPY fetch failed:", e)

today = datetime.date.today().isoformat()
updated, rows = 0, []
for name in sorted(theme2tk):
    members = sorted(theme2tk[name])
    pcts = [(m, price[m]) for m in members if m in price]
    if not pcts:
        continue
    avg = sum(p for _, p in pcts) / len(pcts)
    best = max(pcts, key=lambda x: x[1]); worst = min(pcts, key=lambda x: x[1])
    rows.append((name, len(members), len(pcts), avg, best, worst))
    perf = f"{avg:+.1f}% 1m avg (n={len(pcts)}/{len(members)}); best {best[0]} {best[1]:+.1f}%; worst {worst[0]} {worst[1]:+.1f}%"
    path = os.path.join(THEMES, name + ".md")
    txt = open(path, encoding="utf-8").read()
    fm, body = fm_of(txt)
    new_fm = upsert_fm(fm, [f'last_updated: "{today}"', f'last_perf: "{perf}"', "tracked: true"])
    if new_fm != fm:
        open(path, "w", encoding="utf-8").write("---" + new_fm + "---" + body)
        updated += 1

# --- dated snapshot note ---
rows.sort(key=lambda r: -r[3])
lines = ["# Theme Baskets — 1-month performance", ""]
lines.append(f"SPY 1m: {spy_pct:+.1f}% (yfinance, {today}) · equal-weight basket avgs from company price stamps." if spy_pct is not None else "SPY n/a")
lines.append("")
lines.append("| Basket | n | cov | avg 1m% | best | worst | vs SPY |")
lines.append("|---|---|---|---|---|---|---|")
for name, n, cov, avg, best, worst in rows:
    d = (avg - spy_pct) if spy_pct is not None else 0
    lines.append(f"| {name} | {n} | {cov} | {avg:+.1f}% | {best[0]} {best[1]:+.1f}% | {worst[0]} {worst[1]:+.1f}% | {d:+.1f} |")
lines.append("")
if not rows:
    lines.append("Tracked by theme_tracker.py — no priced baskets found.")
else:
    lines.append(f"Tracked by theme_tracker.py — theme nodes carry .last_perf./.last_updated.. Baskets: {len(rows)}, avg: {sum(r[3] for r in rows)/len(rows):+.1f}%")
fm_note = (
    "---\n"
    'type: "research-note"\n'
    f'date: "{today}"\n'
    'topic: "Theme baskets — 1-month performance tracker"\n'
    'companies: []\n'
    'themes: []\n'
    'context: ["[[Risk appetite]]", "[[Volatility]]"]\n'
    'idea_source: "theme-tracker (auto)"\n'
    'sources: ["[[yfinance]]"]\n'
    'status: "open"\n'
    'importance: 3\n'
    "---\n\n"
)
open(os.path.join(NOTES, f"{today} Theme Baskets.md"), "w", encoding="utf-8").write(fm_note + "\n".join(lines) + "\n")

print(f"theme nodes updated: {updated}/{len(rows)} baskets tracked")
print(f"note: {today} Theme Baskets.md")
print(f"SPY 1m: {spy_pct:+.1f}%" if spy_pct is not None else "SPY n/a")
for name, n, cov, avg, best, worst in rows:
    print(f"  {name:<30} avg {avg:>+6.1f}%  ({cov}/{n})  {best[0]}:{best[1]:+.1f} / {worst[0]}:{worst[1]:+.1f}")