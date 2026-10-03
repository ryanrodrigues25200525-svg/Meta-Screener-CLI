"""Yahoo-backed fundamental screens (fake provider only, no network, no KG reads)."""

from __future__ import annotations

import os
import tempfile
import unittest
import unittest.mock

import pandas as pd


def quarterly_frame(revenues, label="Total Revenue"):
    cols = [f"2024Q{i + 1}" for i in range(len(revenues))]
    return pd.DataFrame({c: {label: v} for c, v in zip(cols, revenues)})


class FakeYahoo:
    """Minimal YahooClient-compatible stub: financials + info only."""

    def __init__(self, frames, infos=None):
        # ticker -> DataFrame (quarterly; reused for annual) or (annual, quarterly)
        self.frames = {k.upper(): v for k, v in frames.items()}
        self.infos = infos or {}

    def _frame(self, ticker, kind):
        entry = self.frames.get(ticker.upper())
        if entry is None:
            return pd.DataFrame()
        if isinstance(entry, tuple):
            annual, quarterly = entry
            return quarterly if kind.startswith("quarterly") else annual
        return entry

    def get_financials(self, ticker, kind="income"):
        return self._frame(ticker, kind)

    def get_info(self, ticker):
        return dict(self.infos.get(ticker.upper(), {
            "shortName": ticker.upper(),
            "marketCap": 10_000_000_000,
            "currency": "USD",
            "financialCurrency": "USD",
        }))


def accelerating_quarterly():
    # QoQ: +10.0%, +13.6%, +20.0%, +25.0% -> accelerating, latest positive
    return quarterly_frame(
        [80_000_000, 88_000_000, 100_000_000, 120_000_000, 150_000_000],
        "Total Revenue",
    )


class RotationYahooTests(unittest.TestCase):
    def test_rotation_yahoo_financials_with_blank_on_missing(self):
        import rotation_screen

        fake = {"AAPL": accelerating_quarterly(), "MSFT": pd.DataFrame()}
        payload = rotation_screen.build_rotation_payload(
            ["AAPL", "MSFT"], provider=FakeYahoo(fake)
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn(
            "blank",
            payload["top"][1]["detail"].lower() + payload["summary"].lower(),
        )

    def test_rotation_works_with_temp_dirs_and_stub_provider(self):
        import rotation_screen

        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "KG_VAULT"}
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with unittest.mock.patch.dict(os.environ, env, clear=True):
                    payload = rotation_screen.build_rotation_payload(
                        ["AAPL"], provider=FakeYahoo({"AAPL": accelerating_quarterly()})
                    )
            finally:
                os.chdir(old_cwd)
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")

    def test_rotation_does_not_read_kg_or_call_yfinance_directly(self):
        import pathlib

        src = pathlib.Path("rotation_screen.py").read_text(encoding="utf-8")
        for banned in ("Companies", "Themes", "fundamentals_", "KG_VAULT",
                       "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


class GrowthMomentumYahooTests(unittest.TestCase):
    def test_growth_yahoo_with_blank_on_missing(self):
        import growth_momentum

        fake = {"AAPL": accelerating_quarterly(), "MSFT": pd.DataFrame()}
        payload = growth_momentum.build_result_payload(
            ["AAPL", "MSFT"], provider=FakeYahoo(fake)
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn(
            "blank",
            payload["top"][1]["detail"].lower() + payload["summary"].lower(),
        )

    def test_growth_works_with_temp_dirs_and_stub_provider(self):
        import growth_momentum

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                payload = growth_momentum.build_result_payload(
                    ["AAPL"], provider=FakeYahoo({"AAPL": accelerating_quarterly()})
                )
            finally:
                os.chdir(old_cwd)
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")

    def test_growth_does_not_read_kg_or_call_yfinance_directly(self):
        import pathlib

        src = pathlib.Path("growth_momentum.py").read_text(encoding="utf-8")
        for banned in ("Companies", "Themes", "fundamentals_", "KG_VAULT",
                       "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
