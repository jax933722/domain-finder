"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.routes import admin, auth, jobs, uploads
from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base
from app.db.models import User, UserRole
from app.db.session import AsyncSessionLocal, engine
from app.core.security import hash_password
from app.services import cache
from app.services.files import ensure_dirs

logger = get_logger(__name__)


async def _init_db() -> None:
    """Create tables if they do not exist and bootstrap the first admin."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.FIRST_ADMIN_EMAIL and settings.FIRST_ADMIN_PASSWORD:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == settings.FIRST_ADMIN_EMAIL.lower())
            )
            if result.scalar_one_or_none() is None:
                session.add(
                    User(
                        email=settings.FIRST_ADMIN_EMAIL.lower(),
                        hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
                        full_name="Administrator",
                        role=UserRole.ADMIN,
                    )
                )
                await session.commit()
                logger.info("Bootstrapped admin user %s", settings.FIRST_ADMIN_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    await _init_db()
    logger.info("%s started in %s mode", settings.PROJECT_NAME, settings.ENVIRONMENT)
    yield
    await cache.close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "Upload a spreadsheet of company names, clean them automatically, and "
        "discover verified official domains from trusted internet sources. "
        "Domains are never guessed — unverifiable companies are reported as NOT FOUND."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(o) for o in settings.BACKEND_CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(uploads.router, prefix=api_prefix)
app.include_router(jobs.router, prefix=api_prefix)
app.include_router(admin.router, prefix=api_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    return {"message": f"{settings.PROJECT_NAME} API", "docs": "/docs"}
