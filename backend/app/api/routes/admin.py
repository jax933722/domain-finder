"""Admin routes: platform-wide statistics and user management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.models import (
    Company,
    Job,
    Upload,
    User,
    VerificationStatus,
)
from app.db.session import get_db
from app.schemas.schemas import AdminStats, JobOut, UserOut
from app.services import cache

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStats)
async def stats(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminStats:
    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    total_jobs = await db.scalar(select(func.count()).select_from(Job)) or 0
    total_uploads = await db.scalar(select(func.count()).select_from(Upload)) or 0
    total_companies = await db.scalar(select(func.count()).select_from(Company)) or 0
    total_found = (
        await db.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.verification_status == VerificationStatus.VERIFIED)
        )
        or 0
    )
    total_not_found = (
        await db.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.verification_status == VerificationStatus.NOT_FOUND)
        )
        or 0
    )
    avg_time = await db.scalar(select(func.avg(Company.processing_time_ms))) or 0.0

    # Top searched companies (by frequency across all jobs).
    top_rows = await db.execute(
        select(Company.clean_company, func.count().label("cnt"))
        .group_by(Company.clean_company)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_companies = [{"company": r[0], "count": r[1]} for r in top_rows.all()]

    # Recent failed lookups.
    failed_rows = await db.execute(
        select(Company.clean_company, Company.reason)
        .where(Company.verification_status == VerificationStatus.NOT_FOUND)
        .order_by(Company.created_at.desc())
        .limit(10)
    )
    failed = [{"company": r[0], "reason": r[1]} for r in failed_rows.all()]

    return AdminStats(
        total_users=total_users,
        total_jobs=total_jobs,
        total_uploads=total_uploads,
        total_companies_processed=total_companies,
        total_found=total_found,
        total_not_found=total_not_found,
        average_processing_time_ms=round(float(avg_time), 2),
        cache=await cache.cache_stats(),
        top_companies=top_companies,
        failed_lookups=failed,
    )


@router.get("/jobs", response_model=list[JobOut])
async def all_jobs(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[JobOut]:
    result = await db.execute(select(Job).order_by(Job.created_at.desc()).limit(200))
    return [JobOut.model_validate(j) for j in result.scalars().all()]


@router.get("/users", response_model=list[UserOut])
async def all_users(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.patch("/users/{user_id}/toggle-active", response_model=UserOut)
async def toggle_active(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")
    user.is_active = not user.is_active
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserOut.model_validate(user)
