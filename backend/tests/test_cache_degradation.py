"""Cache must degrade gracefully when Redis is unavailable."""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services import cache


class _BrokenRedis:
    async def get(self, *a, **k):
        raise RedisConnectionError("redis down")

    async def set(self, *a, **k):
        raise RedisConnectionError("redis down")

    async def lrange(self, *a, **k):
        raise RedisConnectionError("redis down")

    async def ping(self, *a, **k):
        raise RedisConnectionError("redis down")

    def pipeline(self):
        raise RedisConnectionError("redis down")

    async def keys(self, *a, **k):
        raise RedisConnectionError("redis down")

    async def info(self, *a, **k):
        raise RedisConnectionError("redis down")


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    monkeypatch.setattr(cache, "get_redis", lambda: _BrokenRedis())


@pytest.mark.asyncio
async def test_get_returns_none_on_failure():
    assert await cache.get_cached_domain("microsoft") is None


@pytest.mark.asyncio
async def test_set_does_not_raise():
    # Must not raise — a cache write failure cannot break a job.
    await cache.set_cached_domain("microsoft", {"official_domain": "microsoft.com"})


@pytest.mark.asyncio
async def test_progress_and_logs_degrade():
    await cache.set_progress("job1", {"percent": 10})
    assert await cache.get_progress("job1") is None
    await cache.push_log("job1", {"level": "INFO", "message": "hi"})
    assert await cache.get_logs("job1") == []


@pytest.mark.asyncio
async def test_ping_false_when_down():
    assert await cache.ping() is False


@pytest.mark.asyncio
async def test_stats_safe_defaults():
    stats = await cache.cache_stats()
    assert stats["cached_domains"] == 0
    assert stats["hit_rate"] == 0.0
