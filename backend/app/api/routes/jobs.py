"""Job processing routes: start, progress, results, logs, download."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Company, Job, JobStatus, Upload, User
from app.db.session import get_db
from app.schemas.schemas import (
    CompanyResultOut,
    JobOut,
    LogOut,
    ProcessRequest,
    ProgressOut,
    ResultsPage,
)
from app.services import cache
from app.workers.tasks import process_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _owned_job(db: AsyncSession, job_id: uuid.UUID, user: User) -> Job:
    job = await db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/process", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def start_processing(
    payload: ProcessRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    upload = await db.get(Upload, payload.upload_id)
    if not upload or upload.user_id != user.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    if payload.company_column not in upload.columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Column '{payload.company_column}' not present in the uploaded file.",
        )

    job = Job(
        user_id=user.id,
        upload_id=upload.id,
        company_column=payload.company_column,
        status=JobStatus.PENDING,
        total_rows=upload.row_count,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Seed an initial progress record so the UI shows 0% immediately.
    await cache.set_progress(
        str(job.id),
        {
            "job_id": str(job.id),
            "status": JobStatus.PENDING.value,
            "total_rows": job.total_rows,
            "processed_rows": 0,
            "found_count": 0,
            "not_found_count": 0,
            "cache_hits": 0,
            "percent": 0.0,
        },
    )

    # Hand off to the Celery worker. ``.delay`` returns immediately.
    process_job.delay(str(job.id))
    return JobOut.model_validate(job)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    job = await _owned_job(db, job_id, user)
    return JobOut.model_validate(job)


@router.get("", response_model=list[JobOut])
async def list_jobs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[JobOut]:
    result = await db.execute(
        select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc())
    )
    return [JobOut.model_validate(j) for j in result.scalars().all()]


@router.get("/{job_id}/progress", response_model=ProgressOut)
async def get_progress(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressOut:
    job = await _owned_job(db, job_id, user)
    # Prefer the fast Redis snapshot; fall back to the DB record.
    snapshot = await cache.get_progress(str(job_id))
    if snapshot:
        return ProgressOut(**snapshot)
    percent = (job.processed_rows / job.total_rows * 100) if job.total_rows else 0.0
    return ProgressOut(
        job_id=job.id,
        status=job.status.value,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        found_count=job.found_count,
        not_found_count=job.not_found_count,
        cache_hits=job.cache_hits,
        percent=round(percent, 2),
        error=job.error,
    )


@router.get("/{job_id}/results", response_model=ResultsPage)
async def get_results(
    job_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResultsPage:
    job = await _owned_job(db, job_id, user)
    total = await db.scalar(
        select(func.count()).select_from(Company).where(Company.job_id == job_id)
    )
    result = await db.execute(
        select(Company)
        .where(Company.job_id == job_id)
        .order_by(Company.row_index)
        .offset(offset)
        .limit(limit)
    )
    items = [CompanyResultOut.model_validate(c) for c in result.scalars().all()]
    return ResultsPage(
        job=JobOut.model_validate(job),
        total=total or 0,
        offset=offset,
        limit=limit,
        items=items,
    )


@router.get("/{job_id}/logs", response_model=list[LogOut])
async def get_logs(
    job_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LogOut]:
    await _owned_job(db, job_id, user)
    entries = await cache.get_logs(str(job_id), offset=offset)
    return [LogOut(**e) for e in entries]


@router.get("/{job_id}/download")
async def download(
    job_id: uuid.UUID,
    fmt: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _owned_job(db, job_id, user)
    if job.status != JobStatus.COMPLETED or not job.result_path:
        raise HTTPException(status_code=409, detail="Results are not ready yet.")

    base, _ = os.path.splitext(job.result_path)
    path = f"{base}.{fmt}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Result file not found.")

    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if fmt == "xlsx"
        else "text/csv"
    )
    return FileResponse(path, media_type=media, filename=f"enriched_{job_id}.{fmt}")
