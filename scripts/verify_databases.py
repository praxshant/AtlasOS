import sys
import logging
from backend.config import get_settings
from backend.db.postgres import SessionLocal
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client
import redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("atlasos-verifier")

def test_postgres() -> bool:
    logger.info("Testing PostgreSQL connection...")
    try:
        db = SessionLocal()
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        logger.info("✓ PostgreSQL is reachable.")
        db.close()
        return True
    except Exception as e:
        logger.error(f"✗ PostgreSQL connection failed: {e}")
        return False

def test_qdrant() -> bool:
    logger.info("Testing Qdrant connection...")
    try:
        client = qdrant_client.get_client()
        if client:
            client.get_collections()
            logger.info("✓ Qdrant is reachable.")
            return True
        else:
            raise ValueError("Qdrant client not initialized.")
    except Exception as e:
        logger.error(f"✗ Qdrant connection failed: {e}")
        return False

def test_neo4j() -> bool:
    logger.info("Testing Neo4j connection...")
    try:
        driver = neo4j_client.get_driver()
        if driver:
            driver.verify_connectivity()
            logger.info("✓ Neo4j is reachable.")
            return True
        else:
            raise ValueError("Neo4j driver not initialized.")
    except Exception as e:
        logger.error(f"✗ Neo4j connection failed: {e}")
        return False

def test_redis() -> bool:
    logger.info("Testing Redis connection...")
    try:
        settings = get_settings()
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.ping()
        logger.info("✓ Redis is reachable.")
        return True
    except Exception as e:
        logger.error(f"✗ Redis connection failed: {e}")
        return False

def main():
    logger.info("========================================")
    logger.info("ATLASOS Infrastructure Verification Test")
    logger.info("========================================")
    
    pg_ok = test_postgres()
    qdr_ok = test_qdrant()
    neo_ok = test_neo4j()
    red_ok = test_redis()
    
    logger.info("========================================")
    if pg_ok and qdr_ok and neo_ok and red_ok:
        logger.info("ALL INFRASTRUCTURE DATABASES ARE READY!")
        sys.exit(0)
    else:
        logger.error("SOME INFRASTRUCTURE DATABASES FAILED. CHECK LOGS.")
        sys.exit(1)

if __name__ == "__main__":
    main()
