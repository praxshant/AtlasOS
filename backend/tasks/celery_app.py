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
    worker_concurrency=settings.CELERY_CONCURRENCY,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    worker_pool=settings.CELERY_POOL
)

import logging
from celery.signals import worker_process_init

logger = logging.getLogger(__name__)

@worker_process_init.connect
def preload_embedding_model(**kwargs):
    """
    Preloads the sentence-transformers embedding model when the worker process starts.
    This prevents the model from being loaded separately for each task.
    """
    logger.info("Worker process initialized. Preloading embedding model...")
    from backend.vector.qdrant_client import qdrant_client
    qdrant_client._load_embed_model()
    logger.info("Embedding model preloaded successfully.")
