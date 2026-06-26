import logging
from sqlalchemy import text
import redis
from backend.config import get_settings
from backend.db.postgres import SessionLocal
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client

logger = logging.getLogger(__name__)
settings = get_settings()

def verify_startup():
    logger.info("Running ATLASOS startup hardening checks...")
    errors = []

    # 1. OpenRouter key exists
    if not settings.OPENROUTER_API_KEY:
        errors.append("OPENROUTER_API_KEY is missing from environment/settings.")

    # 2. Redis reachable
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.ping()
        logger.info("✓ Redis connection OK")
    except Exception as e:
        errors.append(f"Redis unreachable at {settings.REDIS_URL}: {e}")

    # 3. Postgres reachable
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("✓ Postgres connection OK")
    except Exception as e:
        errors.append(f"PostgreSQL database unreachable: {e}")

    # 4. Neo4j reachable
    try:
        driver = neo4j_client.get_driver()
        if driver:
            driver.verify_connectivity()
            logger.info("✓ Neo4j connection OK")
        else:
            errors.append("Neo4j client could not be initialized.")
    except Exception as e:
        errors.append(f"Neo4j unreachable at {settings.NEO4J_URI}: {e}")

    # 5. Qdrant reachable
    try:
        client = qdrant_client.get_client()
        if client:
            client.get_collections()
            logger.info("✓ Qdrant connection OK")
        else:
            errors.append("Qdrant client could not be initialized.")
    except Exception as e:
        errors.append(f"Qdrant unreachable at {settings.QDRANT_URL}: {e}")

    if errors:
        err_msg = "\n".join(errors)
        logger.critical(f"ATLASOS Startup Hardening check FAILED:\n{err_msg}")
        raise RuntimeError(f"ATLASOS Startup Hardening check FAILED:\n{err_msg}")

    logger.info("✓ All startup hardening checks passed successfully!")
