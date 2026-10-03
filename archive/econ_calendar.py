#!/usr/bin/env python3
"""RETIRED (archived): static approximate macro-event calendar.

Retired because yfinance/Yahoo supplies no macro calendar and the static
KNOWN_EVENTS schedule below is not data — dates must come from official
sources (FRED API, central-bank calendars). Kept for reference only; it is
no longer registered in screeners.json and no screen may depend on it.

Original docstring follows.

Fetch upcoming economic calendar events.

Usage: python3 econ_calendar.py
Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Econ-Calendar.md

Note: Uses yfinance for market dates. For full economic calendar, use FRED API.
"""
import os
from datetime import date, timedelta

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")

# Known recurring events (approximate monthly schedule)
KNOWN_EVENTS = [
    {"event": "FOMC Meeting", "typical": "8x/year, Wed 2pm ET", "impact": "HIGH"},
    {"event": "CPI Report", "typical": "2nd Tue of month", "impact": "HIGH"},
    {"event": "PPI Report", "typical": "3rd Fri of month", "impact": "MEDIUM"},
    {"event": "Jobs Report (NFP)", "typical": "1st Fri of month", "impact": "HIGH"},
    {"event": "Retail Sales", "typical": "~15th of month", "impact": "MEDIUM"},
    {"event": "PMI (ISM Manufacturing)", "typical": "1st business day", "impact": "MEDIUM"},
    {"event": "Consumer Confidence", "typical": "Last Tue of month", "impact": "MEDIUM"},
    {"event": "GDP (Advance)", "typical": "Month after quarter end", "impact": "HIGH"},
]


def write_note(today):
    os.makedirs(KG_NOTES, exist_ok=True)
    lines = [
        "---",
        'type: "market-context"',
        f'date: "{today}"',
        'topic: "Economic calendar — upcoming events"',
        'tags: ["macro", "calendar", "events"]',
        "---",
        "",
        f"# Economic Calendar — {today}",
        "",
        "## Key Recurring Events",
        "",
        "| Event | Typical Schedule | Impact |",
        "|-------|-----------------|--------|",
    ]
    for e in KNOWN_EVENTS:
        lines.append(f"| {e['event']} | {e['typical']} | {e['impact']} |")
    lines.extend([
        "",
        "> For real-time economic calendar, use: https://www.forexfactory.com/calendar",
        "> or FRED API for US economic data releases.",
        "",
    ])
    path = os.path.join(KG_NOTES, f"{today} Econ-Calendar.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {path}")


def main():
    today = date.today().isoformat()
    write_note(today)
    print("Done")


if __name__ == "__main__":
    main()
