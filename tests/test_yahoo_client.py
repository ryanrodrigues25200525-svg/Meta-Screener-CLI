"""Tests for the shared Yahoo serial scheduler/cache (fake provider only, no network)."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path


class TestYahooClient(unittest.TestCase):
    def test_default_provider_falls_back_to_search_when_ticker_news_empty(self):
        import sys
        import types
        import yahoo_client

        stories = [{"title": "t", "publisher": "p", "link": "u", "providerPublishTime": 1}]

        class FakeTicker:
            def __init__(self, ticker):
                self.ticker = ticker

            @property
            def news(self):
                return []

        class FakeSearch:
            def __init__(self, ticker, news_count=10):
                self._stories = stories
                self.ticker = ticker
            @property
            def news(self):
                return self._stories

        fake_yf = types.ModuleType("yfinance")
        fake_yf.Ticker = FakeTicker
        fake_yf.Search = FakeSearch
        old = sys.modules.get("yfinance")
        sys.modules["yfinance"] = fake_yf
        try:
            result = yahoo_client._default_provider("AAPL", op="news")
        finally:
            if old is None:
                del sys.modules["yfinance"]
            else:
                sys.modules["yfinance"] = old
        self.assertEqual(result, stories)

    def test_unreadable_disk_cache_is_a_miss_not_a_failure(self):
        import pickle
        import yahoo_client

        with tempfile.TemporaryDirectory() as tmp:
            client = yahoo_client.YahooClient(
                provider=lambda ticker, **kw: {"ticker": ticker},
                cache_dir=Path(tmp),
            )
            key = yahoo_client._cache_key("info", "AAPL", {})
            path = Path(tmp) / f"yahoo_{key}.pkl"
            with open(path, "wb") as handle:
                pickle.dump((0.0, {"ticker": "STALE"}), handle)
            real_load = pickle.load

            def boom(*args, **kwargs):
                raise ModuleNotFoundError("No module named 'pyarrow'")

            pickle.load = boom
            try:
                self.assertEqual(client.get_info("AAPL"), {"ticker": "AAPL"})
            finally:
                pickle.load = real_load

    def test_new_ops_stop_on_rate_limit_without_retry(self):
        import yahoo_client

        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_fetch(ticker, **kw):
                calls.append(ticker)
                raise Exception("YFRateLimitError: Too Many Requests")

            client = yahoo_client.YahooClient(provider=fake_fetch, cache_dir=Path(tmp))
            for method in ("get_holders", "get_insider", "get_dividends"):
                with self.assertRaises(RuntimeError, msg=method):
                    getattr(client, method)("AAPL")
            self.assertEqual(len(calls), 3)

    def test_shared_client_serializes_and_stops_on_rate_limit(self):
        from yahoo_client import YahooClient

        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_fetch(ticker, **kw):
                calls.append(ticker)
                if ticker == "LIMIT":
                    raise Exception("HTTPError 429 Too Many Requests")
                return {"ticker": ticker}

            client = YahooClient(provider=fake_fetch, cache_dir=Path(tmp))
            self.assertEqual(client.get_info("AAPL")["ticker"], "AAPL")
            with self.assertRaises(RuntimeError):
                client.get_info("LIMIT")
            # cached second call does not refetch
            client.get_info("AAPL")
            self.assertEqual(calls.count("AAPL"), 1)

    def test_disk_cache_survives_new_client(self):
        from yahoo_client import YahooClient

        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_fetch(ticker, **kw):
                calls.append(ticker)
                return {"ticker": ticker}

            first = YahooClient(provider=fake_fetch, cache_dir=Path(tmp))
            first.get_info("MSFT")
            second = YahooClient(provider=fake_fetch, cache_dir=Path(tmp))
            second.get_info("MSFT")
            self.assertEqual(calls.count("MSFT"), 1)

    def test_all_methods_stop_on_rate_limit_without_retry(self):
        from yahoo_client import YahooClient

        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_fetch(ticker, **kw):
                calls.append((ticker, kw.get("op")))
                raise Exception("429 Too Many Requests")

            client = YahooClient(provider=fake_fetch, cache_dir=Path(tmp))
            with self.assertRaises(RuntimeError):
                client.get_history("LIMIT", period="1mo", interval="1d")
            with self.assertRaises(RuntimeError):
                client.get_financials("LIMIT", kind="income")
            with self.assertRaises(RuntimeError):
                client.get_earnings_dates("LIMIT")
            with self.assertRaises(RuntimeError):
                client.get_news("LIMIT")
            # no retry: exactly one provider call per method
            self.assertEqual(len(calls), 4)

    def test_serial_lock_under_threads(self):
        from yahoo_client import YahooClient

        with tempfile.TemporaryDirectory() as tmp:
            active = 0
            max_active = 0
            guard = threading.Lock()

            def fake_fetch(ticker, **kw):
                nonlocal active, max_active
                with guard:
                    active += 1
                    max_active = max(max_active, active)
                try:
                    return {"ticker": ticker}
                finally:
                    with guard:
                        active -= 1

            client = YahooClient(provider=fake_fetch, cache_dir=None)
            threads = [
                threading.Thread(target=client.get_info, args=(f"T{i}",))
                for i in range(10)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(max_active, 1)


if __name__ == "__main__":
    unittest.main()
