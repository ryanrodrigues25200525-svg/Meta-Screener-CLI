#!/usr/bin/env python3
"""important_dates_index.py — generate the [[Important Dates]] hub note from the catalyst notes.

The vault links [[Important Dates]] from catalysts:/sources: arrays, but the folder of 118 catalyst
notes had no hub node, so every one of those links was unresolved. This writes the hub as a real
calendar view: upcoming events first, then recently-passed unhandled ones.

Usage: python3 ~/Documents/finance-ai/important_dates_index.py
"""
import datetime, glob, os, re

VAULT = next(c for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
                         os.path.expanduser("~/Documents/Finance Knowledge Graph"))
             if c and os.path.isdir(c))
SRC = os.path.join(VAULT, "Important Dates")
OUT = os.path.join(VAULT, "Important Dates.md")


def field(fm, key):
    m = re.search(rf'^{key}:\s*"?([^"\n]*)"?\s*$', fm, re.M)
    return (m.group(1).strip() if m else "")


rows = []
for p in glob.glob(os.path.join(SRC, "*.md")):
    txt = open(p, encoding="utf-8", errors="ignore").read()
    parts = txt.split("---", 2)
    if len(parts) < 3:
        continue
    fm = parts[1]
    d = field(fm, "date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        continue
    rows.append({
        "date": d,
        "title": os.path.basename(p)[:-3],
        "company": field(fm, "company").strip("[]"),
        "event": field(fm, "event"),
        "importance": field(fm, "importance"),
        "handled": field(fm, "handled").lower() == "true",
        "outcome": field(fm, "outcome"),
    })

rows.sort(key=lambda r: r["date"])
today = datetime.date.today().isoformat()
upcoming = [r for r in rows if r["date"] >= today]
past_open = [r for r in rows if r["date"] < today and not r["handled"]]
past_done = [r for r in rows if r["date"] < today and r["handled"]]

L = ["---", 'type: "dashboard"', f'date: "{today}"', "generated: true",
     'generator: "important_dates_index.py"', "---", "",
     "# Important Dates", "",
     f"Generated {today} by `important_dates_index.py` from the {len(rows)} catalyst notes in `Important Dates/`. "
     "Edit those notes, not this file.", "",
     f"**{len(upcoming)} upcoming · {len(past_open)} passed but ungraded · {len(past_done)} resolved**", ""]


def block(title, items, show_outcome=False):
    out = [f"## {title}", ""]
    if not items:
        out += ["_None._", ""]
        return out
    out += ["| Date | Event | Company | Imp | Handled |", "|---|---|---|---:|---|"]
    for r in items:
        comp = r["company"] or "—"
        ev = (r["event"] or r["title"])[:70]
        out.append(f"| {r['date']} | [[{r['title']}]] — {ev} | {comp} | {r['importance'] or '—'} | "
                   f"{'yes' if r['handled'] else 'no'} |")
    out.append("")
    return out


L += block("Upcoming", upcoming)
L += block("Passed, not yet graded", past_open)
if past_done:
    L += [f"## Resolved ({len(past_done)})", "",
          "_Most recent 25 — full list is the `Important Dates/` folder._", ""]
    L += ["| Date | Event | Company | Outcome |", "|---|---|---|---|"]
    for r in past_done[-25:]:
        L.append(f"| {r['date']} | [[{r['title']}]] | {r['company'] or '—'} | {r['outcome'] or '—'} |")
    L.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(L))
print(f"wrote {OUT}: {len(upcoming)} upcoming, {len(past_open)} passed-ungraded, {len(past_done)} resolved")
