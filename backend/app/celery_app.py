"""
Celery application configuration for background task processing.

Usage:
    # Start celery worker (from backend directory):
    celery -A app.celery_app worker --loglevel=info --pool=solo

    # On Windows, use solo pool:
    celery -A app.celery_app worker --loglevel=info --pool=solo
"""

from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "docuscan",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.processing"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # Soft limit 9 minutes
    worker_prefetch_multiplier=1,  # Process one task at a time
    result_expires=3600,  # Results expire after 1 hour
)
