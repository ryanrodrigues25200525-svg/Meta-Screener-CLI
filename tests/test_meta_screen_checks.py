"""Tests custom meta-screen check selection and structured ranking output."""

import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


def load_meta_screen_module():
    with tempfile.TemporaryDirectory() as temp_dir:
        stubs = {
            "yfinance": types.ModuleType("yfinance"),
            "pandas": types.ModuleType("pandas"),
            "numpy": types.ModuleType("numpy"),
        }
        with patch.dict(os.environ, {"FINANCE_KG_ROOT": temp_dir}), patch.dict(sys.modules, stubs):
            return importlib.import_module("screeners.meta_signals.meta_screen")


class CheckFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta_screen = load_meta_screen_module()

    def test_selects_only_the_requested_registered_checks(self):
        available = {"first": ("technical", object()), "second": ("quality", object())}

        selected = self.meta_screen.filter_screens(available, ["second"])

        self.assertEqual(list(selected), ["second"])

    def test_rejects_unknown_check_names(self):
        with self.assertRaisesRegex(ValueError, "unknown check"):
            self.meta_screen.filter_screens({"known": object()}, ["missing"])

    def test_rejects_duplicate_check_names(self):
        with self.assertRaisesRegex(ValueError, "must not be repeated"):
            self.meta_screen.filter_screens({"known": object()}, ["known", "known"])

    def test_meta_screen_exports_ranked_rows_to_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "meta-overlap.json"

            self.meta_screen._write_result_json(
                str(result_path), [("ABC", "Example", "demo", [])], 10, "meta-screen.md"
            )
            payload = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["top"][0]["ticker"], "ABC")
        self.assertEqual(payload["top"][0]["name"], "Example")
        self.assertEqual(payload["report_path"], "meta-screen.md")

    def test_meta_screen_uses_fetched_company_name_when_universe_name_is_ticker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "meta-overlap.json"
            data = {"ABC": SimpleNamespace(info={"longName": "Example Incorporated"})}

            self.meta_screen._write_result_json(
                str(result_path), [("ABC", "ABC", "demo", [])], 10, "meta-screen.md", data
            )
            payload = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["top"][0]["name"], "Example Incorporated")


if __name__ == "__main__":
    unittest.main()
