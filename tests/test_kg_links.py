"""Tests that ticker maps and links honor the supplied Finance Knowledge Graph root."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kg_links


class TickerMapTests(unittest.TestCase):
    def test_load_ticker_map_uses_the_passed_knowledge_graph_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            companies = root / "Companies"
            companies.mkdir()
            (companies / "Example Corp.md").write_text(
                "---\nticker: EXM\n---\n# Example Corp\n", encoding="utf-8"
            )

            with patch.object(kg_links, "COMPANIES_DIR", str(root / "unused")):
                ticker_map = kg_links.load_ticker_map(str(root))

        self.assertEqual(ticker_map, {"EXM": "Example Corp"})

    def test_company_link_respects_an_explicit_empty_map_without_fallback(self):
        with patch.object(kg_links, "load_ticker_map", side_effect=AssertionError("unexpected fallback")):
            result = kg_links.company_link("EXM", {})

        self.assertEqual(result, "EXM")

    def test_resolve_company_links_respects_an_explicit_empty_map_without_fallback(self):
        with patch.object(kg_links, "load_ticker_map", return_value={"EXM": "Default Company"}) as load:
            result = kg_links.resolve_company_links(["EXM"], {})

        load.assert_not_called()
        self.assertEqual(result, ["[[EXM]]"])


if __name__ == "__main__":
    unittest.main()
