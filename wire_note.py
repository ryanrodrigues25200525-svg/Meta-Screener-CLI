#!/usr/bin/env python3
"""wire_note.py — link a finished research note into theme nodes, idempotently.

Themes carry a `research:` array of [[note]] links; wiring a note in is a text edit that must be idempotent
and must not break the single-line wikilink rule. Dry-run by default.

Usage:
  python3 wire_note.py --note "2026-09-16 Rotation screen" --themes "Software & SaaS,Cybersecurity,..."
  python3 wire_note.py --note "..." --themes-file /workspace/history/work/rotation_themes.txt --apply
"""
import argparse, os, re

V = "/documents/Finance Knowledge Graph"


def wire(theme, note, apply):
    p = os.path.join(V, "Themes", theme + ".md")
    if not os.path.exists(p):
        return f"{theme}: NO THEME FILE"
    t = open(p, encoding="utf-8").read()
    link = f"[[{note}]]"
    m = re.search(r"^research:\s*\[(.*?)\]\s*$", t, re.M)
    if not m:
        return f"{theme}: no research: array (skipped, left untouched)"
    inner, before = m.group(1), t[:m.start()]
    if link in inner:
        return f"{theme}: already linked ({inner.count('[[')} entries)"
    inner2 = inner.rstrip()
    inner2 = inner2 + (", " if inner2 else "") + '"' + link + '"'
    t2 = before + "research: [" + inner2 + "]" + t[m.end():]
    t2 = re.sub(r'^last_updated:\s*".*?"$', 'last_updated: "2026-09-16"', t2, count=1, flags=re.M)
    # a wikilink must never wrap a line
    if re.search(r"\[\[[^\]]*\n", t2):
        return f"{theme}: REFUSED — would wrap a wikilink across lines"
    if apply:
        open(p, "w", encoding="utf-8").write(t2)
    return f"{theme}: {'linked' if apply else 'would link'} -> now {inner2.count('[[')} entries"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", required=True)
    ap.add_argument("--themes")
    ap.add_argument("--themes-file")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.themes_file:
        themes = [l.strip() for l in open(a.themes_file) if l.strip() and not l.startswith("#")]
    else:
        themes = [x.strip() for x in (a.themes or "").split(",") if x.strip()]
    for th in themes:
        print(wire(th, a.note, a.apply))
