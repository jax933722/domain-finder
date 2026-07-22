"""Prometheus metrics.

Metrics are defined once and imported by both the API and the Celery worker.
Each process maintains its own registry (they run in separate containers), so:

* the **API** exposes ``GET /metrics`` (HTTP + process metrics), and
* the **worker** starts a tiny metrics HTTP server on ``WORKER_METRICS_PORT``
  and increments the job/lookup/provider metrics.

A Prometheus server scrapes both targets (see ``observability/prometheus.yml``).
"""

from __future__ import annotations

import os

from prometheus_client import Counter, Gauge, Histogram

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---- HTTP (API) ----
HTTP_REQUESTS = Counter(
    "df_http_requests_total",
    "Total HTTP requests.",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "df_http_request_duration_seconds",
    "HTTP request latency.",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# ---- Jobs (worker) ----
JOBS_TOTAL = Counter("df_jobs_total", "Jobs by terminal status.", ["status"])
ACTIVE_JOBS = Gauge(
    "df_active_jobs",
    "Jobs currently processing.",
    multiprocess_mode="livesum",  # sum across worker child processes
)
JOB_ROWS = Counter("df_job_rows_total", "Rows processed across all jobs.")

# ---- Domain lookups (worker) ----
LOOKUPS_TOTAL = Counter(
    "df_domain_lookups_total",
    "Company domain lookups by outcome.",
    ["outcome"],  # verified | not_found | cache_hit
)
LOOKUP_LATENCY = Histogram(
    "df_domain_lookup_duration_seconds",
    "Latency of a single company lookup (excludes cache hits).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)

# ---- Search providers (worker) ----
PROVIDER_REQUESTS = Counter(
    "df_provider_requests_total",
    "Search-provider requests by outcome.",
    ["provider", "outcome"],  # success | empty | error
)
PROVIDER_LATENCY = Histogram(
    "df_provider_request_duration_seconds",
    "Search-provider request latency.",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15),
)


def start_worker_metrics_server() -> None:
    """Expose worker metrics over HTTP (best-effort).

    In production the worker runs with ``PROMETHEUS_MULTIPROC_DIR`` set, so each
    prefork child writes samples to that directory and this single HTTP server
    (started once in the worker's main process) aggregates them. Without that
    env var it falls back to the default in-process registry (fine for a
    solo-pool dev worker).
    """
    if not settings.METRICS_ENABLED:
        return
    try:
        from prometheus_client import CollectorRegistry, start_http_server
        from prometheus_client.multiprocess import MultiProcessCollector

        mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
        if mp_dir:
            os.makedirs(mp_dir, exist_ok=True)
            registry = CollectorRegistry()
            MultiProcessCollector(registry)
            start_http_server(settings.WORKER_METRICS_PORT, registry=registry)
        else:
            start_http_server(settings.WORKER_METRICS_PORT)
        logger.info("Worker metrics server listening on :%s", settings.WORKER_METRICS_PORT)
    except OSError as exc:
        logger.debug("Worker metrics server not started: %s", exc)
