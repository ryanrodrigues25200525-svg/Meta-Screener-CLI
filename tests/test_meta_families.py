"""Family-split meta screeners: every --check arg must name a real check (no Yahoo)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_FAMILIES = {
    "meta-momentum": 4,
    "meta-technical": 4,
    "meta-valuation": 5,
    "meta-fundamental": 3,
    "meta-theme": 23,
    "meta-insider": 1,
    "meta-earnings": 1,
    "meta-quality": 6,
}


class TestMetaFamilyScreeners(unittest.TestCase):
    def test_families_grouped_in_meta_signals_stage(self):
        import meta_screener_cli as cli

        registry = cli.read_registry()
        stage_ids = [s["id"] for s in registry["stages"]]
        self.assertIn("meta-signals", stage_ids)
        by_id = {item["id"]: item for item in registry["screeners"]}
        self.assertNotIn("meta-overlap", by_id)
        for family_id in EXPECTED_FAMILIES:
            self.assertEqual(by_id[family_id]["stage"], "meta-signals", family_id)

    def test_family_entries_reference_real_checks(self):
        import meta_screener_cli as cli

        registry = cli.read_registry()
        by_id = {item["id"]: item for item in registry["screeners"]}
        check_names = {name for _, name, _ in cli.meta_screen_checks()}
        total = 0
        for family_id, expected_count in EXPECTED_FAMILIES.items():
            self.assertIn(family_id, by_id, f"missing family screener {family_id}")
            entry = by_id[family_id]
            self.assertTrue(entry["yahoo"], family_id)
            self.assertEqual(entry["file"], "meta_screen.py")
            args = entry.get("args", [])
            checks = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "--check"]
            self.assertEqual(len(checks), expected_count, family_id)
            for name in checks:
                self.assertIn(name, check_names, f"{family_id}: unknown check {name!r}")
            total += len(checks)
        self.assertEqual(total, 47, "families must cover all 47 checks exactly once")
        seen: list[str] = []
        for family_id in EXPECTED_FAMILIES:
            args = by_id[family_id].get("args", [])
            seen.extend(a for i, a in enumerate(args[:-1]) if args[i] == "--check" for a in [args[i + 1]])
        self.assertEqual(len(set(seen)), 47, "check names must not repeat across families")


if __name__ == "__main__":
    unittest.main()
