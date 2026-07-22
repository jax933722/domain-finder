"""Celery task that enriches an uploaded file with official company domains.

Design notes:

* Each Celery task runs its own asyncio event loop (``asyncio.run``) and a single
  async DB engine created inside that loop, so asyncpg connections never leak
  across event loops and we never open an engine-per-row.
* Company lookups fan out with a bounded semaphore for concurrency while
  respecting provider rate limits.
* Duplicate company names are searched only once — the result is reused from an
  in-memory map plus Redis (and the durable ``cached_domains`` table).
* Progress and logs are streamed to Redis so the API can serve real-time
  updates without hammering Postgres.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    CachedDomain,
    Company,
    Job,
    JobStatus,
    Log,
    LogLevel,
    SearchHistory,
    Upload,
    VerificationStatus,
)
from app.services import cache
from app.services.cleaning import cache_key_for, clean_company_name
from app.services.files import read_dataframe, write_results
from app.services.search.discovery import create_http_client, discover_domain
from app.services.search.providers import build_providers
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.process_job", bind=True, max_retries=0)
def process_job(self, job_id: str) -> dict[str, Any]:  # noqa: ANN001
    """Celery entrypoint — synchronous wrapper around the async pipeline."""
    return asyncio.run(_run_job(job_id))


async def _run_job(job_id: str) -> dict[str, Any]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=15, max_overflow=5)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            if job is None:
                logger.error("Job %s not found", job_id)
                return {"status": "missing"}
            # Idempotency: a redelivered task (Celery acks-late) must not double
            # a completed job or duplicate rows.
            if job.status == JobStatus.COMPLETED:
                logger.info("Job %s already completed; skipping.", job_id)
                return {"status": "already_completed"}
            upload = await session.get(Upload, job.upload_id)
            if upload is None:
                await _fail_job(session, job, "Upload record missing.")
                return {"status": "failed"}
            company_column = job.company_column
            stored_path, content_type, filename = (
                upload.stored_path,
                upload.content_type,
                upload.filename,
            )
            # Clear any rows from a previous partial run so results are consistent.
            await session.execute(delete(Company).where(Company.job_id == job.id))
            await session.execute(delete(SearchHistory).where(SearchHistory.job_id == job.id))
            await session.commit()

        await _log(factory, job_id, LogLevel.INFO, "Starting job")
        await _process(factory, job_id, company_column, stored_path, content_type, filename)
        return {"status": "completed"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s crashed", job_id)
        try:
            async with factory() as session:
                job = await session.get(Job, uuid.UUID(job_id))
                if job:
                    await _fail_job(session, job, f"Unexpected error: {exc}")
            await _log(factory, job_id, LogLevel.ERROR, f"Job failed: {exc}")
        except Exception:  # noqa: BLE001
            pass
        return {"status": "failed", "error": str(exc)}
    finally:
        await engine.dispose()
        # Each Celery task runs in a fresh event loop; drop the loop-bound Redis
        # pool so the next task re-creates it in its own loop.
        await cache.close_redis()


async def _process(
    factory: async_sessionmaker[AsyncSession],
    job_id: str,
    company_column: str,
    stored_path: str,
    content_type: str,
    filename: str,
) -> None:
    df = read_dataframe(stored_path, content_type, filename)
    total = len(df)
    raw_values = df[company_column].fillna("").astype(str).tolist()

    providers = build_providers()
    provider_names = ", ".join(p.name for p in providers) or "none configured"
    await _log(factory, job_id, LogLevel.INFO, f"Active search providers: {provider_names}")

    async with factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        session.add(job)
        await session.commit()

    counters = {"processed": 0, "found": 0, "not_found": 0, "cache_hits": 0}
    resolved: dict[str, dict[str, Any]] = {}
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(settings.JOB_CONCURRENCY)

    client = create_http_client()
    try:
        async def handle_row(index: int, raw: str) -> dict[str, Any]:
            async with semaphore:
                return await _resolve_row(
                    factory, job_id, index, raw, providers, client, resolved, lock, counters
                )

        batch_size = 200
        for start in range(0, total, batch_size):
            batch = list(enumerate(raw_values[start : start + batch_size], start=start))
            results = await asyncio.gather(*(handle_row(i, v) for i, v in batch))

            async with factory() as session:
                for res in results:
                    session.add(Company(job_id=uuid.UUID(job_id), **res["company"]))
                    session.add(SearchHistory(job_id=uuid.UUID(job_id), **res["history"]))
                await session.commit()

            await _publish_progress(factory, job_id, total, counters)

        await _log(factory, job_id, LogLevel.INFO, "Writing result files")
        async with factory() as session:
            rows_q = await session.execute(
                select(Company).where(Company.job_id == uuid.UUID(job_id)).order_by(Company.row_index)
            )
            rows = [
                {
                    "original_company": c.original_company,
                    "clean_company": c.clean_company,
                    "official_domain": c.official_domain,
                    "verification_status": c.verification_status.value,
                    "confidence": c.confidence,
                    "source_used": c.source_used,
                    "search_url": c.search_url,
                    "processing_time_ms": c.processing_time_ms,
                }
                for c in rows_q.scalars().all()
            ]
        xlsx_path, _csv_path = write_results(job_id, rows)

        async with factory() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            job.status = JobStatus.COMPLETED
            job.processed_rows = counters["processed"]
            job.found_count = counters["found"]
            job.not_found_count = counters["not_found"]
            job.cache_hits = counters["cache_hits"]
            job.result_path = xlsx_path
            job.finished_at = datetime.now(timezone.utc)
            session.add(job)
            await session.commit()

        await _publish_progress(factory, job_id, total, counters, status=JobStatus.COMPLETED)
        await _log(
            factory,
            job_id,
            LogLevel.INFO,
            f"Completed: {counters['found']} found, {counters['not_found']} not found, "
            f"{counters['cache_hits']} cache hits",
        )
    finally:
        await client.aclose()


async def _resolve_row(
    factory: async_sessionmaker[AsyncSession],
    job_id: str,
    index: int,
    raw: str,
    providers,
    client,
    resolved: dict[str, dict[str, Any]],
    lock: asyncio.Lock,
    counters: dict[str, int],
) -> dict[str, Any]:
    start = time.perf_counter()
    clean = clean_company_name(raw)
    key = cache_key_for(clean)

    from_cache = False
    cached: dict[str, Any] | None = None

    if key:
        async with lock:
            cached = resolved.get(key)
        if cached is None:
            cached = await cache.get_cached_domain(key)
        if cached is not None:
            from_cache = True

    if cached is not None:
        domain = cached.get("official_domain")
        status = cached.get("verification_status", VerificationStatus.NOT_FOUND.value)
        confidence = cached.get("confidence", 0.0)
        source = cached.get("source_used")
        search_url = cached.get("search_url")
        query = cached.get("search_query")
        reason = cached.get("reason")
        provider_used = "cache"
    else:
        result = await discover_domain(clean, providers, client)
        domain = result.domain
        status = result.status
        confidence = result.confidence
        source = result.source
        search_url = result.search_url
        query = result.query
        reason = result.reason
        provider_used = source or "search"

        payload = {
            "official_domain": domain,
            "verification_status": status,
            "confidence": confidence,
            "source_used": source,
            "search_url": search_url,
            "search_query": query,
            "reason": reason,
        }
        if key:
            async with lock:
                resolved[key] = payload
            await cache.set_cached_domain(key, payload)
            await _upsert_cached_domain(factory, key, clean, payload)

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    async with lock:
        counters["processed"] += 1
        if from_cache:
            counters["cache_hits"] += 1
        if status == VerificationStatus.VERIFIED.value:
            counters["found"] += 1
        else:
            counters["not_found"] += 1

    log_msg = (
        f"[{index + 1}] {clean or '(empty)'} -> "
        f"{domain if domain else 'NOT FOUND'}"
        f"{' (cache)' if from_cache else ''}"
    )
    await _log(
        factory, job_id, LogLevel.INFO, log_msg,
        {"row": index, "domain": domain, "confidence": confidence}, persist=False,
    )

    status_enum = (
        VerificationStatus(status)
        if status in {v.value for v in VerificationStatus}
        else VerificationStatus.NOT_FOUND
    )

    return {
        "company": {
            "row_index": index,
            "original_company": raw,
            "clean_company": clean,
            "official_domain": domain,
            "verification_status": status_enum,
            "confidence": float(confidence or 0.0),
            "source_used": source,
            "search_url": search_url,
            "search_query": query,
            "reason": reason,
            "processing_time_ms": elapsed_ms,
            "from_cache": from_cache,
        },
        "history": {
            "clean_company": clean,
            "provider": provider_used,
            "query": query or "",
            "result_domain": domain,
            "success": status == VerificationStatus.VERIFIED.value,
            "response_time_ms": elapsed_ms,
        },
    }


async def _upsert_cached_domain(
    factory: async_sessionmaker[AsyncSession], key: str, clean: str, payload: dict[str, Any]
) -> None:
    """Persist the durable cache record (best-effort; never breaks the row)."""
    try:
        async with factory() as session:
            existing = await session.execute(
                select(CachedDomain).where(CachedDomain.clean_company_key == key)
            )
            row = existing.scalar_one_or_none()
            status_value = payload.get("verification_status", VerificationStatus.NOT_FOUND.value)
            status_enum = (
                VerificationStatus(status_value)
                if status_value in {v.value for v in VerificationStatus}
                else VerificationStatus.NOT_FOUND
            )
            if row is None:
                session.add(
                    CachedDomain(
                        clean_company_key=key,
                        clean_company=clean,
                        official_domain=payload.get("official_domain"),
                        verification_status=status_enum,
                        confidence=float(payload.get("confidence", 0.0) or 0.0),
                        source_used=payload.get("source_used"),
                        hit_count=0,
                    )
                )
            else:
                row.hit_count += 1
                session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache upsert failed for %s: %s", key, exc)


async def _publish_progress(
    factory: async_sessionmaker[AsyncSession],
    job_id: str,
    total: int,
    counters: dict[str, int],
    status: JobStatus = JobStatus.RUNNING,
) -> None:
    percent = round(counters["processed"] / total * 100, 2) if total else 100.0
    snapshot = {
        "job_id": job_id,
        "status": status.value,
        "total_rows": total,
        "processed_rows": counters["processed"],
        "found_count": counters["found"],
        "not_found_count": counters["not_found"],
        "cache_hits": counters["cache_hits"],
        "percent": percent,
    }
    await cache.set_progress(job_id, snapshot)

    async with factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job:
            job.processed_rows = counters["processed"]
            job.found_count = counters["found"]
            job.not_found_count = counters["not_found"]
            job.cache_hits = counters["cache_hits"]
            session.add(job)
            await session.commit()


async def _fail_job(session: AsyncSession, job: Job, message: str) -> None:
    job.status = JobStatus.FAILED
    job.error = message
    job.finished_at = datetime.now(timezone.utc)
    session.add(job)
    await session.commit()
    await cache.set_progress(
        str(job.id),
        {
            "job_id": str(job.id),
            "status": JobStatus.FAILED.value,
            "total_rows": job.total_rows,
            "processed_rows": job.processed_rows,
            "found_count": job.found_count,
            "not_found_count": job.not_found_count,
            "cache_hits": job.cache_hits,
            "percent": 0.0,
            "error": message,
        },
    )


async def _log(
    factory: async_sessionmaker[AsyncSession],
    job_id: str,
    level: LogLevel,
    message: str,
    context: dict[str, Any] | None = None,
    persist: bool = True,
) -> None:
    """Push a log line to Redis (live UI) and optionally persist to Postgres.

    Per-row logs set ``persist=False`` to avoid flooding Postgres; milestone
    logs are persisted for the durable audit trail.
    """
    entry = {
        "level": level.value,
        "message": message,
        "context": context or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await cache.push_log(job_id, entry)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to push log to Redis: %s", exc)

    if not persist:
        return
    try:
        async with factory() as session:
            session.add(
                Log(job_id=uuid.UUID(job_id), level=level, message=message, context=context or {})
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist log: %s", exc)
