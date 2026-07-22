"""Tests for the async token-bucket rate limiter."""

import time

import pytest

from app.services.search.ratelimit import TokenBucket, get_limiter, reset


@pytest.fixture(autouse=True)
def _clean():
    reset()
    yield
    reset()


@pytest.mark.asyncio
async def test_zero_rate_is_unlimited():
    bucket = TokenBucket(rate_per_sec=0)
    start = time.perf_counter()
    for _ in range(1000):
        await bucket.acquire()
    assert time.perf_counter() - start < 0.5


@pytest.mark.asyncio
async def test_throttles_to_rate():
    # capacity 1, 50 tokens/sec -> ~0.02s between acquisitions after the first.
    bucket = TokenBucket(rate_per_sec=50, capacity=1)
    start = time.perf_counter()
    for _ in range(5):
        await bucket.acquire()
    elapsed = time.perf_counter() - start
    # 4 waits * 0.02s = 0.08s; allow slack but require real throttling occurred.
    assert elapsed >= 0.05


@pytest.mark.asyncio
async def test_limiter_is_per_provider_singleton():
    a1 = get_limiter("brave")
    a2 = get_limiter("brave")
    b1 = get_limiter("bing")
    assert a1 is a2
    assert a1 is not b1
