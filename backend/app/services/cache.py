"""Redis-backed caching and live job-progress store.

Two responsibilities:

* **Domain cache** — resolved domains keyed by the cleaned company slug so a
  company is only searched once (e.g. "Microsoft" is reused everywhere).
* **Job progress / logs** — fast, ephemeral counters and a capped log stream
  that the ``/progress`` and ``/logs`` endpoints poll for real-time updates.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_DOMAIN_PREFIX = "domain:"
_PROGRESS_PREFIX = "progress:"
_LOG_PREFIX = "logs:"
_MAX_LOG_ENTRIES = 500

_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


# Redis is a performance/UX layer, not the source of truth (Postgres is). A
# transient Redis outage must degrade to a cache-miss, never crash a job — so
# every operation is wrapped and failures are logged and swallowed.
_RedisFailure = (RedisError, OSError, asyncio.TimeoutError)


async def ping() -> bool:
    """Readiness probe helper — True if Redis responds."""
    try:
        return bool(await get_redis().ping())
    except _RedisFailure:
        return False


# --------------------------------------------------------------------------- #
# Domain cache
# --------------------------------------------------------------------------- #
async def get_cached_domain(key: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().get(_DOMAIN_PREFIX + key)
    except _RedisFailure as exc:
        logger.warning("Redis get failed (treating as miss): %s", exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def set_cached_domain(key: str, payload: dict[str, Any], ttl: int | None = None) -> None:
    try:
        await get_redis().set(
            _DOMAIN_PREFIX + key,
            json.dumps(payload),
            ex=ttl if ttl is not None else settings.DOMAIN_CACHE_TTL_SECONDS,
        )
    except _RedisFailure as exc:
        logger.warning("Redis set failed (skipping cache write): %s", exc)


async def cache_stats() -> dict[str, Any]:
    try:
        redis = get_redis()
        keys = await redis.keys(_DOMAIN_PREFIX + "*")
        info = await redis.info("stats")
    except _RedisFailure as exc:
        logger.warning("Redis stats unavailable: %s", exc)
        return {"cached_domains": 0, "keyspace_hits": 0, "keyspace_misses": 0, "hit_rate": 0.0}
    hits = int(info.get("keyspace_hits", 0))
    misses = int(info.get("keyspace_misses", 0))
    total = hits + misses
    return {
        "cached_domains": len(keys),
        "keyspace_hits": hits,
        "keyspace_misses": misses,
        "hit_rate": round(hits / total, 4) if total else 0.0,
    }


# --------------------------------------------------------------------------- #
# Job progress
# --------------------------------------------------------------------------- #
async def set_progress(job_id: str, payload: dict[str, Any], ttl: int = 60 * 60 * 24) -> None:
    try:
        await get_redis().set(_PROGRESS_PREFIX + job_id, json.dumps(payload), ex=ttl)
    except _RedisFailure as exc:
        logger.warning("Redis progress write failed: %s", exc)


async def get_progress(job_id: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().get(_PROGRESS_PREFIX + job_id)
    except _RedisFailure as exc:
        logger.warning("Redis progress read failed: %s", exc)
        return None
    return json.loads(raw) if raw else None


# --------------------------------------------------------------------------- #
# Live logs (capped list)
# --------------------------------------------------------------------------- #
async def push_log(job_id: str, entry: dict[str, Any], ttl: int = 60 * 60 * 24) -> None:
    try:
        redis = get_redis()
        key = _LOG_PREFIX + job_id
        pipe = redis.pipeline()
        pipe.rpush(key, json.dumps(entry))
        pipe.ltrim(key, -_MAX_LOG_ENTRIES, -1)
        pipe.expire(key, ttl)
        await pipe.execute()
    except _RedisFailure as exc:
        logger.warning("Redis log push failed: %s", exc)


async def get_logs(job_id: str, offset: int = 0) -> list[dict[str, Any]]:
    try:
        raw = await get_redis().lrange(_LOG_PREFIX + job_id, offset, -1)
    except _RedisFailure as exc:
        logger.warning("Redis log read failed: %s", exc)
        return []
    out = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return out
