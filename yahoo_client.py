"""Shared Yahoo Finance access: serial scheduler, cache, and rate-limit stop.

This module is the ONLY allowed path for Yahoo Finance data in this repo.
Do not call ``yfinance.Ticker`` (``yf.Ticker``) directly from any screener
or helper script — always go through :class:`YahooClient` or the
module-level ``get_history`` / ``get_info`` / ``get_financials`` /
``get_earnings_dates`` / ``get_news`` / ``get_options`` /
``get_option_chain`` helpers below.

Rules (global constraints):
- All fetches are serialized through one process-wide ``threading.Lock``.
- Results are cached in memory and on disk (TTL 24h) so repeated screens
  do not hammer Yahoo.
- On rate-limit markers the fetch fails fast with ``RuntimeError`` telling
  the caller to stop the screen and retry after a cooldown. No retry and
  no ``time.sleep`` here.
- Missing/blank data is returned as-is; consumers handle blanks.
- Tests must inject a fake ``provider``; no Yahoo calls in tests.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from yahoo_guard import raise_if_yahoo_rate_limit

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

CACHE_TTL_SECONDS = 24 * 60 * 60

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / ".meta-screener" / "cache"

# Process-wide serial scheduler: every Yahoo fetch in this process,
# regardless of which YahooClient instance issues it, holds this lock.
_SERIAL_LOCK = threading.Lock()

Provider = Callable[..., Any]


def _cache_key(op: str, ticker: str, kwargs: dict[str, Any]) -> str:
    payload = json.dumps(
        {"op": op, "ticker": ticker.upper(), "kwargs": kwargs},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_FINANCIALS_ATTRS = {
    "income": "financials",
    "annual": "financials",
    "quarterly-income": "quarterly_financials",
    "quarterly": "quarterly_financials",
    "balance": "balance_sheet",
    "annual-balance": "balance_sheet",
    "quarterly-balance": "quarterly_balance_sheet",
    "cashflow": "cashflow",
    "annual-cashflow": "cashflow",
    "quarterly-cashflow": "quarterly_cashflow",
}


def _financials_attr(kind: str) -> str:
    """Map a statement-kind spelling to the yfinance attribute name.

    Accepts both the ``income``/``quarterly-income`` spellings used by
    :meth:`YahooClient.get_financials` and the ``annual``/``quarterly``
    spellings used in the screen briefs. Unknown kinds fall back to the
    annual income statement (pre-existing behaviour).
    """
    return _FINANCIALS_ATTRS.get(kind, "financials")


def _default_provider(ticker: str, op: str = "info", **kwargs: Any) -> Any:
    """Live Yahoo provider via yfinance. Only used when no provider is injected."""
    import yfinance as yf

    stock = yf.Ticker(ticker)
    if op == "info":
        return stock.info
    if op == "history":
        return stock.history(
            period=kwargs.get("period", "1y"),
            interval=kwargs.get("interval", "1d"),
            auto_adjust=False,
        )
    if op == "financials":
        return getattr(stock, _financials_attr(kwargs.get("kind", "income")))
    if op == "earnings_dates":
        return stock.get_earnings_dates(limit=kwargs.get("limit", 12))
    if op == "news":
        stories = stock.news or []
        if not stories:
            search = yf.Search(ticker, news_count=kwargs.get("count", 10))
            stories = search.news or []
        return stories
    if op == "options":
        expirations = stock.options
        return list(expirations) if expirations else []
    if op == "option_chain":
        chain = stock.option_chain(date=kwargs.get("expiry"))
        calls = getattr(chain, "calls", None)
        puts = getattr(chain, "puts", None)
        if isinstance(chain, dict):
            calls = chain.get("calls", calls)
            puts = chain.get("puts", puts)
        return {"calls": calls, "puts": puts}
    raise ValueError(f"Unknown Yahoo op: {op}")


class YahooClient:
    """Serial, cached, fail-fast Yahoo Finance client.

    :param provider: callable ``provider(ticker, op=..., **kwargs)``.
        Defaults to the live yfinance provider. Tests inject a fake.
    :param cache_dir: directory for on-disk cache. ``None`` disables
        disk caching (in-memory cache still applies).
    :param ttl: cache time-to-live in seconds (default 24h).
    """

    def __init__(
        self,
        provider: Provider | None = None,
        cache_dir: Path | str | None = _DEFAULT_CACHE_DIR,
        ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._provider = provider or _default_provider
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._ttl = ttl
        self._memory: dict[str, tuple[float, Any]] = {}

    # -- public API ----------------------------------------------------
    def get_info(self, ticker: str) -> dict:
        return self._fetch("info", ticker)

    def get_history(
        self,
        ticker: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        return self._fetch("history", ticker, period=period, interval=interval)

    def get_financials(self, ticker: str, kind: str = "income") -> pd.DataFrame:
        return self._fetch("financials", ticker, kind=kind)

    def get_earnings_dates(
        self, ticker: str, limit: int = 12
    ) -> pd.DataFrame:
        return self._fetch("earnings_dates", ticker, limit=limit)

    def get_news(self, ticker: str) -> list[dict]:
        return self._fetch("news", ticker)

    def get_options(self, ticker: str) -> list:
        """Listed option expiration dates for one ticker (possibly empty)."""
        return self._fetch("options", ticker)

    def get_option_chain(self, ticker: str, expiry: Any = None) -> dict:
        """Option chain for one ticker/expiry as ``{"calls": df, "puts": df}``."""
        return self._fetch("option_chain", ticker, expiry=expiry)

    # -- internals -----------------------------------------------------
    def _fetch(self, op: str, ticker: str, **kwargs: Any) -> Any:
        key = _cache_key(op, ticker, kwargs)
        context = f"yahoo {op} for {ticker}"
        with _SERIAL_LOCK:
            hit = self._memory.get(key)
            if hit is not None:
                timestamp, value = hit
                if time.time() - timestamp < self._ttl:
                    return value
                del self._memory[key]
            if self._cache_dir is not None:
                cached = self._read_disk(key)
                if cached is not None:
                    self._memory[key] = (time.time(), cached)
                    return cached
            try:
                value = self._provider(ticker, op=op, **kwargs)
            except Exception as exc:
                raise_if_yahoo_rate_limit(exc, context)
                raise
            # Never cache empty story lists: a transiently empty news
            # response must not poison the cache for a full TTL.
            if not (op == "news" and value == []):
                self._memory[key] = (time.time(), value)
                if self._cache_dir is not None:
                    self._write_disk(key, value)
            return value

    def _disk_path(self, key: str) -> Path:
        assert self._cache_dir is not None
        return self._cache_dir / f"yahoo_{key}.pkl"

    def _read_disk(self, key: str) -> Any | None:
        path = self._disk_path(key)
        try:
            with open(path, "rb") as handle:
                timestamp, value = pickle.load(handle)
        except Exception:
            # Cache is best-effort: an unreadable entry (missing optional
            # dependency, corrupt bytes, newer pickle protocol) is a miss,
            # never a screen failure. Remove it so the next read refetches.
            try:
                path.unlink()
            except OSError:
                pass
            return None
        if time.time() - timestamp >= self._ttl:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        return value

    def _write_disk(self, key: str, value: Any) -> None:
        assert self._cache_dir is not None
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self._disk_path(key), "wb") as handle:
                pickle.dump((time.time(), value), handle)
        except OSError:
            pass


_default_client: YahooClient | None = None


def _shared_client() -> YahooClient:
    global _default_client
    if _default_client is None:
        _default_client = YahooClient()
    return _default_client


def get_info(ticker: str) -> dict:
    return _shared_client().get_info(ticker)


def get_history(
    ticker: str, period: str = "1y", interval: str = "1d"
) -> pd.DataFrame:
    return _shared_client().get_history(ticker, period=period, interval=interval)


def get_financials(ticker: str, kind: str = "income") -> pd.DataFrame:
    return _shared_client().get_financials(ticker, kind=kind)


def get_earnings_dates(ticker: str, limit: int = 12) -> pd.DataFrame:
    return _shared_client().get_earnings_dates(ticker, limit=limit)


def get_news(ticker: str) -> list[dict]:
    return _shared_client().get_news(ticker)


def get_options(ticker: str) -> list:
    return _shared_client().get_options(ticker)


def get_option_chain(ticker: str, expiry: Any = None) -> dict:
    return _shared_client().get_option_chain(ticker, expiry=expiry)
