"""FastAPI application entrypoint."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select, text

from app.core.logging import request_id_ctx
from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS

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


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Attach a correlation id and record request metrics/latency."""
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    token = request_id_ctx.set(req_id)
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        # Use the matched route template to keep metric label cardinality low
        # (so /jobs/{id}/progress is one series, not one per job id).
        route = request.scope.get("route")
        path = getattr(route, "path_format", None) or getattr(route, "path", None) or "unmatched"
        elapsed = time.perf_counter() - start
        if settings.METRICS_ENABLED:
            HTTP_REQUESTS.labels(request.method, path, str(status_code)).inc()
            HTTP_LATENCY.labels(request.method, path).observe(elapsed)
        request_id_ctx.reset(token)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint (API process metrics)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

api_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(uploads.router, prefix=api_prefix)
app.include_router(jobs.router, prefix=api_prefix)
app.include_router(admin.router, prefix=api_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness: the process is up and serving."""
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get("/health/ready", tags=["health"])
async def readiness() -> JSONResponse:
    """Readiness: dependencies (Postgres + Redis) are reachable."""
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Readiness DB check failed: %s", exc)

    redis_ok = await cache.ping()
    ready = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"ready": ready, "database": db_ok, "redis": redis_ok},
    )


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    return {"message": f"{settings.PROJECT_NAME} API", "docs": "/docs"}
