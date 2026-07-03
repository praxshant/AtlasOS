"""
AtlasOS Migration 002: Add Processing Job Details

This migration:
1. Adds `details` column to `processing_jobs` table as JSONB with default '{}'
"""

import sys
import logging
from sqlalchemy import create_engine, text
from backend.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration-002")

settings = get_settings()

def run_migration():
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.begin() as conn:
        logger.info("=" * 60)
        logger.info("AtlasOS Migration 002: Add Processing Job Details")
        logger.info("=" * 60)
        
        logger.info("[Step 1/1] Adding details column to processing_jobs...")
        try:
            conn.execute(text("""
                ALTER TABLE processing_jobs
                ADD COLUMN IF NOT EXISTS details JSONB DEFAULT '{}'::jsonb;
            """))
            logger.info("  ✓ Added details column to processing_jobs")
        except Exception as e:
            logger.error(f"  ✗ Failed to add details column: {e}")
            raise

        logger.info("=" * 60)
        logger.info("Migration 002 completed successfully!")
        logger.info("=" * 60)

if __name__ == "__main__":
    run_migration()
