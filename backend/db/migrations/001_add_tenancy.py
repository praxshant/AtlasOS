"""
AtlasOS Migration 001: Add Multi-Tenancy Support

This migration:
1. Creates the `tenants` table
2. Inserts a 'default' tenant for existing data
3. Adds `tenant_id` column to all relevant tables
4. Backfills existing rows with the default tenant ID
5. Creates composite indexes for tenant-scoped queries
6. Adds NOT NULL constraints after backfill

Usage:
    python -m backend.db.migrations.001_add_tenancy
"""

import sys
import logging
from sqlalchemy import create_engine, text
from backend.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration-001")

settings = get_settings()

DEFAULT_TENANT_ID = "default"
DEFAULT_TENANT_NAME = "Default Organization"
DEFAULT_TENANT_SLUG = "default"

# Tables that need tenant_id
TENANT_TABLES = [
    "users",
    "documents",
    "processing_jobs",
    "chunks",
    "entities",
    "audit_logs",
]

def run_migration():
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.begin() as conn:
        logger.info("=" * 60)
        logger.info("AtlasOS Migration 001: Add Multi-Tenancy")
        logger.info("=" * 60)
        
        # -------------------------------------------------------
        # Step 1: Create tenants table
        # -------------------------------------------------------
        logger.info("[Step 1/6] Creating tenants table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tenants (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                slug VARCHAR UNIQUE NOT NULL,
                plan VARCHAR DEFAULT 'free',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        logger.info("  ✓ tenants table created")
        
        # -------------------------------------------------------
        # Step 2: Insert default tenant
        # -------------------------------------------------------
        logger.info("[Step 2/6] Inserting default tenant...")
        conn.execute(text("""
            INSERT INTO tenants (id, name, slug, plan, is_active)
            VALUES (:id, :name, :slug, 'free', TRUE)
            ON CONFLICT (id) DO NOTHING;
        """), {"id": DEFAULT_TENANT_ID, "name": DEFAULT_TENANT_NAME, "slug": DEFAULT_TENANT_SLUG})
        logger.info(f"  ✓ Default tenant '{DEFAULT_TENANT_ID}' ensured")
        
        # -------------------------------------------------------
        # Step 3: Add tenant_id columns (nullable first)
        # -------------------------------------------------------
        logger.info("[Step 3/6] Adding tenant_id columns...")
        for table in TENANT_TABLES:
            try:
                # Check if column already exists
                result = conn.execute(text(f"""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = :table AND column_name = 'tenant_id';
                """), {"table": table})
                if result.fetchone() is None:
                    conn.execute(text(f"""
                        ALTER TABLE {table} 
                        ADD COLUMN tenant_id VARCHAR REFERENCES tenants(id);
                    """))
                    logger.info(f"  ✓ Added tenant_id to {table}")
                else:
                    logger.info(f"  ○ tenant_id already exists on {table}")
            except Exception as e:
                logger.error(f"  ✗ Failed to add tenant_id to {table}: {e}")
                raise
        
        # -------------------------------------------------------
        # Step 4: Backfill existing rows with default tenant
        # -------------------------------------------------------
        logger.info("[Step 4/6] Backfilling existing rows...")
        for table in TENANT_TABLES:
            result = conn.execute(text(f"""
                UPDATE {table} SET tenant_id = :tenant_id WHERE tenant_id IS NULL;
            """), {"tenant_id": DEFAULT_TENANT_ID})
            logger.info(f"  ✓ Backfilled {result.rowcount} rows in {table}")
        
        # -------------------------------------------------------
        # Step 5: Set NOT NULL constraints
        # -------------------------------------------------------
        logger.info("[Step 5/6] Setting NOT NULL constraints...")
        for table in TENANT_TABLES:
            try:
                conn.execute(text(f"""
                    ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL;
                """))
                logger.info(f"  ✓ tenant_id NOT NULL on {table}")
            except Exception as e:
                # May already be NOT NULL
                logger.warning(f"  ○ Could not set NOT NULL on {table}: {e}")
        
        # -------------------------------------------------------
        # Step 6: Create composite indexes
        # -------------------------------------------------------
        logger.info("[Step 6/6] Creating composite indexes...")
        indexes = [
            ("ix_users_tenant", "users", "tenant_id, id"),
            ("ix_users_tenant_username", "users", "tenant_id, username"),
            ("ix_documents_tenant", "documents", "tenant_id, id"),
            ("ix_documents_tenant_status", "documents", "tenant_id, status"),
            ("ix_processing_jobs_tenant", "processing_jobs", "tenant_id, id"),
            ("ix_chunks_tenant_doc", "chunks", "tenant_id, document_id"),
            ("ix_entities_tenant_name", "entities", "tenant_id, canonical_name"),
            ("ix_entities_tenant_type", "entities", "tenant_id, entity_type"),
            ("ix_audit_logs_tenant_time", "audit_logs", "tenant_id, timestamp"),
        ]
        
        for idx_name, table, columns in indexes:
            try:
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns});
                """))
                logger.info(f"  ✓ Index {idx_name} on {table}({columns})")
            except Exception as e:
                logger.warning(f"  ○ Index {idx_name} may already exist: {e}")
        
        logger.info("=" * 60)
        logger.info("Migration 001 completed successfully!")
        logger.info("=" * 60)

if __name__ == "__main__":
    run_migration()
