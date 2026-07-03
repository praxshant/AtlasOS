from celery import Celery
from backend.config import get_settings
from backend.utils.startup_checks import verify_startup
from backend.db.postgres import init_db, ensure_default_tenant

# Run startup hardening checks
verify_startup()

# Ensure Postgres schemas and default tenant exist for background processing
init_db()
ensure_default_tenant()

settings = get_settings()

celery_app = Celery(
    "atlasos_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["backend.tasks.ingestion_tasks"]
)

import os

is_windows = os.name == 'nt'

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_concurrency=1 if is_windows else 4,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    worker_pool='solo' if is_windows else 'prefork'
)

import logging
from celery.signals import worker_process_init

logger = logging.getLogger(__name__)

# Eager model loading removed in favor of lazy loading with thread lock
