"""Redis-backed caching and live job-progress store.

Two responsibilities:

* **Domain cache** — resolved domains keyed by the cleaned company slug so a
  company is only searched once (e.g. "Microsoft" is reused everywhere).
* **Job progress / logs** — fast, ephemeral counters and a capped log stream
  that the ``/progress`` and ``/logs`` endpoints poll for real-time updates.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

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


# --------------------------------------------------------------------------- #
# Domain cache
# --------------------------------------------------------------------------- #
async def get_cached_domain(key: str) -> dict[str, Any] | None:
    redis = get_redis()
    raw = await redis.get(_DOMAIN_PREFIX + key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def set_cached_domain(key: str, payload: dict[str, Any], ttl: int | None = None) -> None:
    redis = get_redis()
    await redis.set(
        _DOMAIN_PREFIX + key,
        json.dumps(payload),
        ex=ttl if ttl is not None else settings.DOMAIN_CACHE_TTL_SECONDS,
    )


async def cache_stats() -> dict[str, Any]:
    redis = get_redis()
    keys = await redis.keys(_DOMAIN_PREFIX + "*")
    info = await redis.info("stats")
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
    redis = get_redis()
    await redis.set(_PROGRESS_PREFIX + job_id, json.dumps(payload), ex=ttl)


async def get_progress(job_id: str) -> dict[str, Any] | None:
    redis = get_redis()
    raw = await redis.get(_PROGRESS_PREFIX + job_id)
    return json.loads(raw) if raw else None


# --------------------------------------------------------------------------- #
# Live logs (capped list)
# --------------------------------------------------------------------------- #
async def push_log(job_id: str, entry: dict[str, Any], ttl: int = 60 * 60 * 24) -> None:
    redis = get_redis()
    key = _LOG_PREFIX + job_id
    pipe = redis.pipeline()
    pipe.rpush(key, json.dumps(entry))
    pipe.ltrim(key, -_MAX_LOG_ENTRIES, -1)
    pipe.expire(key, ttl)
    await pipe.execute()


async def get_logs(job_id: str, offset: int = 0) -> list[dict[str, Any]]:
    redis = get_redis()
    key = _LOG_PREFIX + job_id
    raw = await redis.lrange(key, offset, -1)
    out = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return out
