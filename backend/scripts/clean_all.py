import os
import sys
import shutil
import logging
import subprocess

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.db.postgres import SessionLocal, Document, Chunk, Entity, AuditLog, ProcessingJob, User
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client
from backend.config import get_settings
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_postgres():
    try:
        db = SessionLocal()
        logger.info("Cleaning PostgreSQL tables...")
        # Order matters for foreign keys: chunks and entities reference documents
        db.query(Chunk).delete()
        db.query(Entity).delete()
        db.query(AuditLog).delete()
        db.query(ProcessingJob).delete()
        db.query(Document).delete()
        db.commit()
        db.close()
        logger.info("PostgreSQL cleanup complete.")
    except Exception as e:
        logger.error(f"PostgreSQL cleanup failed: {e}")

def clean_neo4j():
    try:
        logger.info("Cleaning Neo4j graph...")
        neo4j_client.run_query("MATCH (n) DETACH DELETE n")
        logger.info("Neo4j cleanup complete.")
    except Exception as e:
        logger.error(f"Neo4j cleanup failed: {e}")

def clean_qdrant():
    try:
        settings = get_settings()
        collection_name = settings.QDRANT_COLLECTION_NAME
        logger.info(f"Cleaning Qdrant collection: {collection_name}...")
        client = qdrant_client.get_client()
        client.delete_collection(collection_name)
        logger.info("Qdrant cleanup complete.")
    except Exception as e:
        logger.error(f"Qdrant cleanup failed: {e}")

def clean_redis():
    try:
        settings = get_settings()
        logger.info("Cleaning Redis cache...")
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.flushall()
        logger.info("Redis cleanup complete.")
    except Exception as e:
        logger.error(f"Redis cleanup failed: {e}")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def clean_celery():
    try:
        logger.info("Purging Celery queues...")
        subprocess.run(
            [sys.executable, "-m", "celery", "-A", "backend.tasks.celery_app", "purge", "-f"], 
            cwd=PROJECT_ROOT, 
            check=True
        )
        logger.info("Celery cleanup complete.")
    except Exception as e:
        logger.error(f"Celery cleanup failed: {e}")

def clean_directories():
    base_dir = PROJECT_ROOT
    
    # 1. Clean .next directory
    next_dir = os.path.join(base_dir, 'frontend', '.next')
    if os.path.exists(next_dir):
        logger.info(f"Removing {next_dir}...")
        shutil.rmtree(next_dir, ignore_errors=True)
        
    # 2. Clean __pycache__
    logger.info("Removing __pycache__ directories...")
    for root, dirs, files in os.walk(base_dir):
        for d in dirs:
            if d == '__pycache__':
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)

if __name__ == "__main__":
    logger.info("Starting Comprehensive System Cleanup...")
    clean_postgres()
    clean_neo4j()
    clean_qdrant()
    clean_redis()
    clean_celery()
    clean_directories()
    logger.info("System cleanup finished.")
