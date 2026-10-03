"""Tests structured ticker rankings from the screener result adapters."""

import importlib
import json
import os
import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def import_without_yahoo(module_name):
    yahoo_stub = types.ModuleType("yfinance")
    with patch.dict(sys.modules, {"yfinance": yahoo_stub}):
        return importlib.import_module(module_name)


def import_rotation_screen():
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch.dict(os.environ, {"KG_VAULT": temp_dir}):
            return importlib.import_module("screeners.discovery.rotation_screen")


class RankedResultTests(unittest.TestCase):
    def test_fundamental_rotation_result_uses_shortlist_rank_order(self):
        rotation_screen = import_rotation_screen()
        rows = [
            {"ticker": "SLOW", "name": "Slow Corp", "qoq_last": 0.05, "om_last": 0.10, "ps_ttm": 2.0},
            {"ticker": "FAST", "name": "Fast Corp", "qoq_last": 0.20, "om_last": 0.15, "ps_ttm": 1.5},
        ]

        result = rotation_screen.build_result_payload(rows, "rotation.csv")

        self.assertEqual([row["ticker"] for row in result["top"]], ["FAST", "SLOW"])
        self.assertEqual(result["top"][0]["rank"], 1)
        self.assertEqual(result["report_path"], "rotation.csv")

    def test_short_interest_result_ranks_highest_float_short_first_and_caps_at_ten(self):
        short_interest = import_without_yahoo("screeners.company_signals.short_interest")
        rows = [
            {"ticker": f"T{i}", "short_pct": i, "short_ratio": 2.0, "flag": "NORMAL"}
            for i in range(12)
        ]

        result = short_interest.build_result_payload(rows, "short-interest.md")

        self.assertEqual(len(result["top"]), 10)
        self.assertEqual(result["top"][0]["ticker"], "T11")
        self.assertEqual(result["top"][0]["rank"], 1)
        self.assertEqual(result["report_path"], "short-interest.md")

    def test_short_interest_writes_ranked_rows_without_changing_report_path(self):
        short_interest = import_without_yahoo("screeners.company_signals.short_interest")
        rows = [
            {"ticker": "LOW", "short_pct": 5.0, "short_ratio": 1.0, "shares_short": 100, "flag": "NORMAL"},
            {"ticker": "HIGH", "short_pct": 25.0, "short_ratio": 4.0, "shares_short": 200, "flag": "HIGH"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            notes_dir = Path(temp_dir) / "Notes"
            result_path = Path(temp_dir) / "short-interest.json"
            with patch.object(short_interest, "NOTES_DIR", str(notes_dir)):
                note_path = short_interest.write_note("2026-10-03", rows, str(result_path))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(Path(note_path).is_file())
            self.assertEqual(result["top"][0]["ticker"], "HIGH")
            self.assertEqual(result["report_path"], note_path)

    def test_dividend_result_ranks_yield_high_to_low(self):
        dividend_analysis = import_without_yahoo("screeners.company_signals.dividend_analysis")
        rows = [
            {"ticker": "LOW", "yield": 1.2, "rate": 0.8, "payout": 20.0},
            {"ticker": "HIGH", "yield": 5.4, "rate": 3.2, "payout": 60.0},
        ]

        result = dividend_analysis.build_result_payload(rows, "dividend.md")

        self.assertEqual([row["ticker"] for row in result["top"]], ["HIGH", "LOW"])
        self.assertIn("5.4%", result["top"][0]["detail"])

    def test_dividend_analysis_writes_ranked_rows_for_the_existing_note(self):
        dividend_analysis = import_without_yahoo("screeners.company_signals.dividend_analysis")
        rows = [
            {"ticker": "LOW", "yield": 1.2, "rate": 0.8, "payout": 20.0},
            {"ticker": "HIGH", "yield": 5.4, "rate": 3.2, "payout": 60.0},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            notes_dir = Path(temp_dir) / "Notes"
            result_path = Path(temp_dir) / "dividend-analysis.json"
            with patch.object(dividend_analysis, "NOTES_DIR", str(notes_dir)):
                note_path = dividend_analysis.write_note("2026-10-03", rows, str(result_path))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(Path(note_path).is_file())
            self.assertEqual(result["top"][0]["ticker"], "HIGH")
            self.assertEqual(result["report_path"], note_path)


if __name__ == "__main__":
    unittest.main()
