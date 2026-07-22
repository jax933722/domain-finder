"""Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    # Returned only in non-production so the flow is testable without email.
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# --------------------------------------------------------------------------- #
# Uploads
# --------------------------------------------------------------------------- #
class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    row_count: int
    columns: list[str]
    preview: list[dict[str, Any]]
    created_at: datetime


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
class ProcessRequest(BaseModel):
    upload_id: uuid.UUID
    company_column: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    upload_id: uuid.UUID
    company_column: str
    status: str
    total_rows: int
    processed_rows: int
    found_count: int
    not_found_count: int
    cache_hits: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ProgressOut(BaseModel):
    job_id: uuid.UUID
    status: str
    total_rows: int
    processed_rows: int
    found_count: int
    not_found_count: int
    cache_hits: int
    percent: float
    error: str | None = None


class CompanyResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_index: int
    original_company: str
    clean_company: str
    official_domain: str | None
    verification_status: str
    confidence: float
    source_used: str | None
    search_url: str | None
    search_query: str | None
    reason: str | None
    processing_time_ms: int
    from_cache: bool


class ResultsPage(BaseModel):
    job: JobOut
    total: int
    offset: int
    limit: int
    items: list[CompanyResultOut]


class LogOut(BaseModel):
    level: str
    message: str
    context: dict[str, Any] = {}
    timestamp: str | None = None


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
class AdminStats(BaseModel):
    total_users: int
    total_jobs: int
    total_uploads: int
    total_companies_processed: int
    total_found: int
    total_not_found: int
    average_processing_time_ms: float
    cache: dict[str, Any]
    top_companies: list[dict[str, Any]]
    failed_lookups: list[dict[str, Any]]
