"""Async token-bucket rate limiting, shared per provider across a worker.

At scale, many concurrent company lookups hit the same search provider. A global
per-provider limiter smooths that burst to a sustainable requests/second so we
don't trip provider rate limits (HTTP 429). Limiters are process-wide singletons
keyed by provider name.
"""

from __future__ import annotations

import asyncio
import time

from app.core.config import settings


class TokenBucket:
    """A simple asyncio token-bucket rate limiter."""

    def __init__(self, rate_per_sec: float, capacity: float | None = None):
        self.rate = rate_per_sec
        self.capacity = capacity if capacity is not None else max(1.0, rate_per_sec)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.rate <= 0:
            return  # unlimited
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                # Wait just long enough for the next token to accrue.
                deficit = 1 - self._tokens
                await asyncio.sleep(deficit / self.rate)


_buckets: dict[str, TokenBucket] = {}


def get_limiter(provider: str) -> TokenBucket:
    bucket = _buckets.get(provider)
    if bucket is None:
        bucket = TokenBucket(settings.PROVIDER_RATE_LIMIT_PER_SEC)
        _buckets[provider] = bucket
    return bucket


async def acquire(provider: str) -> None:
    await get_limiter(provider).acquire()


def reset() -> None:
    """Clear all limiters — used by tests."""
    _buckets.clear()
