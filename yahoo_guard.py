"""Shared fail-fast handling for Yahoo Finance rate-limit exceptions."""

from __future__ import annotations


_RATE_LIMIT_MARKERS = (
    "too many requests",
    "rate limit",
    "rate-limit",
    "ratelimit",
    "yfratelimit",
    "429",
)


def is_yahoo_rate_limit(error: BaseException) -> bool:
    message = f"{type(error).__name__}: {error}".lower()
    return any(marker in message for marker in _RATE_LIMIT_MARKERS)


def raise_if_yahoo_rate_limit(error: BaseException, context: str) -> None:
    """Reraise throttling failures so loops stop instead of silently continuing."""
    if is_yahoo_rate_limit(error):
        raise RuntimeError(
            f"Yahoo rate limit detected during {context}; stop this screen and retry after cooldown."
        ) from error
