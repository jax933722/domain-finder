"""Celery application factory.

Redis is used as both broker and result backend. Company processing is
CPU-light but IO-heavy (network searches), so each task drives its own asyncio
event loop to fan out concurrent lookups.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "domain_finder",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
)
