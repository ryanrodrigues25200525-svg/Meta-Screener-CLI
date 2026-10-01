#!/usr/bin/env python3
"""
Catalyst calendar scan — reads the Important Dates/ folder of the Knowledge
Graph and writes ~/Documents/Finance Knowledge Graph/Notes/<today> Catalysts.md
with events in the coming window.

Usage: python3 catalyst_scan.py [--days 21]
"""
import os, sys, glob, argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    args = ap.parse_args()

    events = kg_links.upcoming_catalysts(horizon_days=args.days, from_days=0)
    today = date.today().isoformat()
    _write_note(today, events, args.days)


def _write_note(today, events, days):
    os.makedirs(KG_NOTES, exist_ok=True)
    import json
    front = (
        "---\n"
        f'type: "research-note"\n'
        f'date: "{today}"\n'
        f'topic: "Upcoming catalysts — {len(events)} events in next {days}d"\n'
        'companies: []\n'
        'themes: [""]\n'
        'context: [""]\n'
        'sources: [""]\n'
        'status: "open"\n'
        'importance: 5\n'
        "---\n\n"
    )
    body = [f"# Upcoming Catalysts {today}\n",
            f"Events in next {days} days from the Important Dates calendar:\n",
            "| Date | Imp | Event | Company |\n|---|---|---|---|"]
    for e in events:
        body.append(f"| {e['date']} | {e['importance']} | {e['event']} | {e['company']} |")
    body.append("\n## What these mean for tracked theses\n")
    body.append("- Check each event against its linked thesis before it lands.")
    body.append("- Earnings/catalyst events can confirm OR invalidate a thesis — that's the kill-switch trigger point.\n")
    body.append("## Detail\n")
    for e in events:
        theses = e.get("theses") or ""
        notes = e.get("notes") or ""
        body.append(f"### {e['date']} — {e['company']} {e['event']}")
        if theses:
            body.append(f"- Theses touched: {theses}")
        if notes:
            body.append(f"- {notes}")
        body.append("")
    title = os.path.join(KG_NOTES, f"{today} Catalysts.md")
    with open(title, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", title)
    for e in events:
        print(" ", e["date"], e["event"], e["company"])


if __name__ == "__main__":
    main()
