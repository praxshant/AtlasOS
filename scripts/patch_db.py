from backend.db.postgres import SessionLocal
from sqlalchemy import text

def patch_db():
    db = SessionLocal()
    try:
        # Add actor_type
        db.execute(text("ALTER TABLE audit_logs ADD COLUMN actor_type VARCHAR DEFAULT 'USER';"))
        # Add actor_name
        db.execute(text("ALTER TABLE audit_logs ADD COLUMN actor_name VARCHAR;"))
        db.commit()
        print("Successfully added actor_type and actor_name to audit_logs.")
    except Exception as e:
        print(f"Error patching DB (maybe already patched?): {e}")
    finally:
        db.close()

if __name__ == "__main__":
    patch_db()
