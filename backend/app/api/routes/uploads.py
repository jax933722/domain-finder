"""File upload routes."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Upload, User
from app.db.session import get_db
from app.schemas.schemas import UploadOut
from app.services.files import dataframe_preview, ensure_dirs, read_dataframe

logger = get_logger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])

_ALLOWED_EXT = (".csv", ".xlsx", ".xlsm", ".xls")


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadOut:
    filename = file.filename or "upload"
    if not filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Upload a .csv or .xlsx file.",
        )

    ensure_dirs()
    upload_id = uuid.uuid4()
    ext = os.path.splitext(filename)[1].lower()
    stored_path = os.path.join(settings.UPLOAD_DIR, f"{upload_id}{ext}")

    # Stream to disk with a hard size cap to protect the server.
    size = 0
    try:
        with open(stored_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    out.close()
                    os.remove(stored_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds {settings.MAX_UPLOAD_BYTES // (1024*1024)} MB limit.",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if os.path.exists(stored_path):
            os.remove(stored_path)
        logger.exception("Failed to store upload")
        raise HTTPException(status_code=500, detail=f"Could not store file: {exc}") from exc

    # Parse for columns + preview.
    try:
        df = read_dataframe(stored_path, file.content_type or "", filename)
    except Exception as exc:  # noqa: BLE001
        os.remove(stored_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse file: {exc}",
        ) from exc

    if len(df) == 0:
        os.remove(stored_path)
        raise HTTPException(status_code=422, detail="The uploaded file has no rows.")
    if len(df) > settings.MAX_UPLOAD_ROWS:
        os.remove(stored_path)
        raise HTTPException(
            status_code=422,
            detail=f"File has {len(df)} rows; the maximum is {settings.MAX_UPLOAD_ROWS}.",
        )

    preview = dataframe_preview(df)
    upload = Upload(
        id=upload_id,
        user_id=user.id,
        filename=filename,
        stored_path=stored_path,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        row_count=len(df),
        columns=preview["columns"],
        preview=preview["rows"],
    )
    db.add(upload)
    await db.flush()
    await db.refresh(upload)
    return UploadOut.model_validate(upload)


@router.get("", response_model=list[UploadOut])
async def list_uploads(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UploadOut]:
    result = await db.execute(
        select(Upload).where(Upload.user_id == user.id).order_by(Upload.created_at.desc())
    )
    return [UploadOut.model_validate(u) for u in result.scalars().all()]


@router.get("/{upload_id}", response_model=UploadOut)
async def get_upload(
    upload_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadOut:
    upload = await db.get(Upload, upload_id)
    if not upload or upload.user_id != user.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    return UploadOut.model_validate(upload)
