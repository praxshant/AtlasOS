import os

file_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\tasks\ingestion_tasks.py"

new_code = """
def _run_async(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, loop).result()
    except RuntimeError:
        pass
    return asyncio.run(coro)

@celery_app.task(bind=True, max_retries=3)
def extract_entities_task(self, prev: dict):
    if not prev: return None
    logger.info(f"[DAG] extract_entities_task (bulk graph build) for {prev['job_id']}")
    db = SessionLocal()
    try:
        job, doc = get_job_and_doc(db, prev['job_id'], prev['tenant_id'], prev['document_id'])
        set_status_and_publish(db, doc, "entity_extraction", prev['tenant_id'])
        
        db_chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
        texts = [c.text_content for c in db_chunks]
        
        from backend.ingestion.entity_extractor import extract_entities_batched
        results = _run_async(extract_entities_batched(texts))
        
        all_entities: dict[str, dict] = {}
        all_rels: list[dict] = []
        for idx, res in enumerate(results):
            for e in res.entities:
                key = e["name"]
                if key not in all_entities:
                    e["canonical_id"] = key
                    e["tenant_id"] = prev['tenant_id']
                    e["document_id"] = doc.id
                    all_entities[key] = e
            for r in res.relationships:
                r["tenant_id"] = prev['tenant_id']
                r["document_id"] = doc.id
                all_rels.append(r)
                
        entities = list(all_entities.values())
        
        from backend.graph.neo4j_client import neo4j_client as nc
        stats = nc.bulk_upsert(
            tenant_id=prev['tenant_id'],
            entities=entities,
            relationships=all_rels,
        )
        logger.info(
            "Doc %s graph build: %d entities, %d rels, created %s",
            doc.id, len(entities), len(all_rels), stats,
        )
        
        return prev
    except Exception as e:
        db.rollback()
        if 'job' in locals() and job: job.status = "failed"; job.error = str(e)
        if 'doc' in locals() and doc: set_status_and_publish(db, doc, "failed", prev['tenant_id'])
        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3)
def extract_relationships_task(self, prev: dict):
    # Skipped since entities task builds the whole graph now
    return prev

@celery_app.task(bind=True, max_retries=3)
def graph_upsert_task(self, prev: dict):
    # Skipped since entities task builds the whole graph now
    return prev
"""

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

import re
# Remove the old extract_entities_task, extract_relationships_task, graph_upsert_task
content = re.sub(
    r'@celery_app\.task\(bind=True, max_retries=3\)\ndef extract_entities_task\(self, prev: dict\):.*?(?=@celery_app\.task\(bind=True, max_retries=3\)\ndef quality_validation_task)',
    new_code + '\n',
    content,
    flags=re.DOTALL
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched ingestion_tasks.py")
