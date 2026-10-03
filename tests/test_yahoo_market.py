"""Market-breadth and meta-overlap Yahoo-only tests (fake provider only).

No Yahoo network calls, no Finance Knowledge Graph reads: every test injects
a fake provider (or patches ``yahoo_client.get_history``) and runs in temp
directories.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


def fake_prices(start=100.0, days=220, step=1.0):
    """Rising daily closes as a yfinance-style history frame."""
    idx = pd.date_range("2025-01-01", periods=days, freq="B")
    closes = [start + i * step for i in range(days)]
    return pd.DataFrame({"Close": closes}, index=idx)


class FakeYahoo:
    """Minimal YahooClient-compatible stub: history + info only."""

    def __init__(self, closes, infos=None):
        self.closes = closes
        self.infos = infos or {}

    def get_history(self, ticker, period="6mo", interval="1d"):
        frame = self.closes.get(ticker.upper())
        if frame is None:
            return pd.DataFrame()
        return frame

    def get_info(self, ticker):
        return dict(self.infos.get(ticker.upper(), {"shortName": ticker.upper()}))

    def get_earnings_dates(self, ticker, limit=12):
        return pd.DataFrame()

    def get_financials(self, ticker, kind="income"):
        return pd.DataFrame()


class BreadthYahooTests(unittest.TestCase):
    def test_breadth_uses_yahoo_prices_not_local_files(self):
        import breadth_rotation

        with patch("yahoo_client.get_history", return_value=fake_prices()):
            result = breadth_rotation.compute_breadth(["AAPL", "MSFT"])
        self.assertIn("breadth", result["summary"].lower())

    def test_breadth_with_injected_provider_and_blank_on_missing(self):
        import breadth_rotation

        provider = FakeYahoo({"AAPL": fake_prices()})
        result = breadth_rotation.compute_breadth(["AAPL", "MSFT"], provider=provider)
        self.assertIn("breadth", result["summary"].lower())
        tickers = [row["ticker"] for row in result["top"]]
        self.assertIn("AAPL", tickers)
        self.assertIn("blank", result["summary"].lower())

    def test_breadth_works_with_temp_dirs_and_stub_provider(self):
        import breadth_rotation

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                result = breadth_rotation.compute_breadth(
                    ["AAPL"], provider=FakeYahoo({"AAPL": fake_prices()})
                )
            finally:
                os.chdir(old_cwd)
        self.assertIn("breadth", result["summary"].lower())

    def test_breadth_does_not_read_kg_or_call_yfinance_directly(self):
        import pathlib

        src = pathlib.Path("breadth_rotation.py").read_text(encoding="utf-8")
        for banned in ("prices_monthly", "Themes", "/documents/", "KG_ROOT", "VAULT",
                       "KG_VAULT", "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker(", "glob.glob"):
            self.assertNotIn(banned, src)


class MetaOverlapYahooTests(unittest.TestCase):
    def test_meta_universe_defaults_without_kg_and_accepts_csv_selection(self):
        import meta_screen

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                default = meta_screen.load_universe(None)
                self.assertTrue(len(default) > 10)
                csv_path = os.path.join(tmp, "universe.csv")
                with open(csv_path, "w", encoding="utf-8") as handle:
                    handle.write("ticker,name,theme\nAAPL,Apple,demo\n")
                selected = meta_screen.load_universe(csv_path)
                self.assertEqual([t for t, _, _ in selected], ["AAPL"])
            finally:
                os.chdir(old_cwd)

    def test_meta_theme_rotation_uses_yahoo_provider(self):
        import meta_screen

        provider = FakeYahoo({
            "SPY": fake_prices(start=400.0),
            "SMH": fake_prices(start=200.0, step=2.0),
        })
        hot, rate_limited = meta_screen.theme_rotation(provider=provider, pause_seconds=0)
        self.assertFalse(rate_limited)
        self.assertIn("semis/AI", hot)

    def test_meta_does_not_use_kg_links_or_yfinance_directly(self):
        import pathlib

        src = pathlib.Path("meta_screen.py").read_text(encoding="utf-8")
        for banned in ("kg_links", "load_ticker_map", "company_link", "UNIVERSE_FILE",
                       "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
