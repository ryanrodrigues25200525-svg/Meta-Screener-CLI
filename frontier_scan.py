#!/usr/bin/env python3
"""
frontier_scan.py — collects every "what's still open" question across the
Finance Knowledge Graph research notes and writes a ranked frontier note to
~/Documents/Finance Knowledge Graph/Notes/<today> Frontier.md.

This is the "make the graph an active work queue" job.

Usage: python3 frontier_scan.py
"""
import os, sys, glob, re, argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")

# Important-dates horizon used to surface linked catalysts.
FRONTIER_HORIZON_DAYS = 45


def main():
    today = date.today().isoformat()
    questions = []
    for path in sorted(glob.glob(os.path.join(KG_NOTES, "*.md"))):
        fm = kg_links.get_frontmatter(path)
        text = open(path, encoding="utf-8").read()
        note_title = os.path.splitext(os.path.basename(path))[0]
        status = (fm.get("status") or "").lower()
        imp = fm.get("importance")
        try:
            imp = int(imp) if imp else 3
        except Exception:
            imp = 3
        if status in ("closed", "complete"):
            continue
        # find "## What's still open" section bullets
        m = re.search(r"##\s*What's still open\s*(.*?)(?=\n##\s|\Z)", text, re.S)
        if not m:
            continue
        for bullet in re.findall(r"^[-*]\s+(.+)$", m.group(1), re.M):
            bullet = bullet.strip()
            if bullet and not bullet.startswith("<!--"):
                questions.append((imp, note_title, bullet))
    # rank by importance desc
    questions.sort(key=lambda q: -q[0])
    _write_note(today, questions)


def _write_note(today, questions):
    os.makedirs(KG_NOTES, exist_ok=True)
    front = (
        "---\n"
        f'type: "research-note"\n'
        f'date: "{today}"\n'
        f'topic: "Frontier scan — active open questions across the graph"\n'
        'companies: []\n'
        'themes: [""]\n'
        'context: [""]\n'
        'sources: [""]\n'
        'status: "open"\n'
        'importance: 5\n'
        "---\n\n"
    )
    body = [f"# Frontier {today}\n",
            "Active open questions from **every** research note — the graph's work queue.\n",
            f"## Top open questions ({len(questions)} across graph)\n",
            "| Imp | Source note | Open question |\n|---|---|---|"]
    for imp, note, q in questions:
        body.append(f"| {imp} | {note} | {q} |")
    body.append("\n## Follow-ups\n- Cross-check each high-importance question against current data before closing.")
    body.append("- Any question looked answered since its source note was written should be closed in that note.\n")
    title = os.path.join(KG_NOTES, f"{today} Frontier.md")
    with open(title, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", title)
    print(f"open questions: {len(questions)}")


if __name__ == "__main__":
    main()
