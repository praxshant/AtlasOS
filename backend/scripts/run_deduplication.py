import os
import sys
import argparse
import hashlib
from typing import Dict, List

# Add project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.db.postgres import SessionLocal, Document, ProcessingJob
from backend.config import get_settings
from backend.tasks.ingestion_tasks import delete_document_task

settings = get_settings()

def calculate_hash(filepath: str) -> str:
    """Calculate SHA-256 hash of a file."""
    if not os.path.exists(filepath):
        return None
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        # Read in blocks of 64kb
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def run_deduplication(dry_run: bool = True):
    db = SessionLocal()
    try:
        # 1. Backfill missing file hashes
        print("--- PHASE 1: Backfilling missing hashes ---")
        legacy_docs = db.query(Document).filter(
            Document.file_hash == None,
            Document.status != "deleted"
        ).all()
        
        if not legacy_docs:
            print("No legacy documents missing file_hash.")
        else:
            print(f"Found {len(legacy_docs)} documents missing file_hash. Computing...")
            for doc in legacy_docs:
                filepath = os.path.join(settings.UPLOAD_DIR, doc.filename)
                file_hash = calculate_hash(filepath)
                if file_hash:
                    doc.file_hash = file_hash
                    print(f"  [OK] Hashed {doc.filename} -> {file_hash[:8]}...")
                else:
                    print(f"  [WARN] File not found for {doc.filename} at {filepath}")
            
            if not dry_run:
                db.commit()
                print("Database updated with backfilled hashes.")
            else:
                print("[DRY RUN] Database commit skipped for backfill.")
        
        # 2. Identify duplicate groups
        print("\n--- PHASE 2: Identifying Duplicates ---")
        # Get all active documents
        active_docs = db.query(Document).filter(
            Document.status != "deleted",
            Document.file_hash != None
        ).all()
        
        # Group by (tenant_id, file_hash)
        groups: Dict[tuple, List[Document]] = {}
        for doc in active_docs:
            key = (doc.tenant_id, doc.file_hash)
            groups.setdefault(key, []).append(doc)
            
        duplicates_found = False
        
        for (tenant_id, file_hash), docs in groups.items():
            if len(docs) > 1:
                duplicates_found = True
                # Sort by upload time (oldest first)
                sorted_docs = sorted(docs, key=lambda d: d.upload_time)
                primary = sorted_docs[0]
                duplicates = sorted_docs[1:]
                
                print(f"\nDuplicate Group Found (Tenant: {tenant_id}, Hash: {file_hash[:8]}...):")
                print(f"  Primary (Kept): ID {primary.id} - '{primary.filename}' (Uploaded: {primary.upload_time})")
                
                for dup in duplicates:
                    print(f"  Duplicate (To Delete): ID {dup.id} - '{dup.filename}' (Uploaded: {dup.upload_time})")
                    
                    if not dry_run:
                        print(f"    -> Enqueueing deletion task for {dup.filename}...")
                        filepath = os.path.join(settings.UPLOAD_DIR, dup.filename)
                        
                        # Create a deletion job
                        job = ProcessingJob(
                            tenant_id=tenant_id,
                            document_id=dup.id,
                            job_type="deletion",
                            status="pending"
                        )
                        db.add(job)
                        db.commit()
                        db.refresh(job)
                        
                        # Enqueue Celery task
                        delete_document_task.delay(str(job.id), tenant_id, dup.id, filepath)
                        print(f"    -> Deletion job {job.id} enqueued successfully.")
                        
        if not duplicates_found:
            print("\nNo duplicates found in the system. Graph is clean!")
            
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AtlasOS Background Deduplication Script")
    parser.add_argument("--cleanup", action="store_true", help="Actually execute the deletion tasks")
    args = parser.parse_args()
    
    dry_run = not args.cleanup
    print(f"Starting Deduplication Script (Dry Run: {dry_run})\n{'='*50}")
    run_deduplication(dry_run)
