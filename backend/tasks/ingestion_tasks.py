import logging
import os as _sys_os
import json
import time as _time
import redis
from typing import Dict, Any, List

from backend.tasks.celery_app import celery_app
from backend.tasks.progress_tracker import progress_tracker
from backend.db.postgres import SessionLocal, ProcessingJob, Document, Chunk, Entity, AuditLog
from backend.ingestion.document_processor import process_document
from backend.ingestion.entity_extractor import extract_entities_batched
from backend.graph.graph_builder import build_graph_from_extraction
from backend.graph.neo4j_client import neo4j_client as _neo4j_client
from backend.vector.qdrant_client import qdrant_client
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def publish_document_status(doc, tenant_id: str):
    try:
        r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        r.publish(f"documents:{tenant_id}", json.dumps({
            "event": "document_update",
            "document": {
                "id": doc.id,
                "filename": doc.filename,
                "status": doc.status,
                "file_type": doc.file_type,
                "upload_time": doc.upload_time.isoformat() if hasattr(doc.upload_time, 'isoformat') else str(doc.upload_time)
            }
        }))
    except Exception as e:
        logger.warning(f"Failed to publish document status to SSE: {e}")


def get_job_and_doc(db, job_id, tenant_id, document_id=None):
    from backend.db.postgres import ProcessingJob, Document
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id, ProcessingJob.tenant_id == tenant_id).first()
    if not job:
        return None, None
    doc_id = document_id or job.document_id
    doc = db.query(Document).filter(Document.id == doc_id, Document.tenant_id == tenant_id).first()
    return job, doc

def set_status_and_publish(db, doc, status, tenant_id):
    doc.status = status
    db.commit()
    publish_document_status(doc, tenant_id)

@celery_app.task(bind=True, max_retries=3)
def validate_task(self, job_id: str, tenant_id: str):
    logger.info(f"[DAG] validate_task for {job_id}")
    db = SessionLocal()
    try:
        job, doc = get_job_and_doc(db, job_id, tenant_id)
        if not doc: return None
        set_status_and_publish(db, doc, "validating", tenant_id)
        # Validation logic (e.g. magic bytes) would go here
        
        # Start timing for the overall job and parsing
        return {
            "job_id": job_id, 
            "document_id": doc.id, 
            "tenant_id": tenant_id,
            "start_time": _time.time(),
            "parse_start": _time.time()
        }
    except Exception as e:
        db.rollback()
        job.status = "failed"
        job.error = str(e)
        if 'doc' in locals() and doc: set_status_and_publish(db, doc, "failed", tenant_id)
        raise self.retry(exc=e, countdown=5)
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3)
def parse_and_chunk_task(self, prev: dict):
    if not prev: return None
    logger.info(f"[DAG] parse_and_chunk_task for {prev['job_id']}")
    db = SessionLocal()
    try:
        job, doc = get_job_and_doc(db, prev['job_id'], prev['tenant_id'], prev['document_id'])
        set_status_and_publish(db, doc, "parsing", prev['tenant_id'])
        
        chunks_data = process_document(file_path=doc.file_path, document_id=doc.id)
        if not chunks_data:
            raise ValueError("No text extracted from document")
            
        # Optional: update job details with risk signals
        risk_chunks = [c for c in chunks_data if c.get("metadata", {}).get("has_risk_signal", False)]
        job.details = json.dumps({"risk_signals_found": len(risk_chunks)})
        
        # Save chunks to DB without Qdrant ID first
        db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
        for i, chunk in enumerate(chunks_data):
            db.add(Chunk(
                tenant_id=prev['tenant_id'], document_id=doc.id, page_number=chunk["page_number"],
                chunk_index=i, text_content=chunk["text"],
            ))
        db.commit()
        prev["parse_time_ms"] = (_time.time() - prev.get("parse_start", _time.time())) * 1000
        prev["embed_start"] = _time.time()
        return prev
    except Exception as e:
        db.rollback()
        if 'job' in locals() and job: job.status = "failed"; job.error = str(e)
        if 'doc' in locals() and doc: set_status_and_publish(db, doc, "failed", prev['tenant_id'])
        raise self.retry(exc=e, countdown=5)
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3)
def embed_task(self, prev: dict):
    if not prev: return None
    logger.info(f"[DAG] embed_task for {prev['job_id']}")
    db = SessionLocal()
    try:
        job, doc = get_job_and_doc(db, prev['job_id'], prev['tenant_id'], prev['document_id'])
        set_status_and_publish(db, doc, "embedding", prev['tenant_id'])
        
        db_chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
        qdrant_chunks = []
        for c in db_chunks:
            qdrant_chunks.append({
                "text": c.text_content, "doc_id": doc.id, "page": c.page_number, "chunk_index": c.chunk_index,
                "metadata": {"source_file": doc.filename}
            })
        
        qdrant_ids = qdrant_client.upsert_chunks(settings.QDRANT_COLLECTION_NAME, qdrant_chunks, tenant_id=prev['tenant_id'])
        
        for c, q_id in zip(db_chunks, qdrant_ids):
            c.qdrant_id = q_id
        db.commit()
        
        prev["embed_time_ms"] = (_time.time() - prev.get("embed_start", _time.time())) * 1000
        prev["llm_start"] = _time.time()
        return prev
    except Exception as e:
        db.rollback()
        if 'job' in locals() and job: job.status = "failed"; job.error = str(e)
        if 'doc' in locals() and doc: set_status_and_publish(db, doc, "failed", prev['tenant_id'])
        raise self.retry(exc=e, countdown=5)
    finally:
        db.close()


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
        
        from backend.ingestion.entity_extractor import extract_entities_one_call
        full_text = "\n\n".join(texts)
        result = extract_entities_one_call(full_text, tenant_id=prev['tenant_id'], doc_id=doc.id)
        
        entities = result.get("entities", [])
        all_rels = result.get("relationships", [])
        
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
        
        prev["llm_time_ms"] = (_time.time() - prev.get("llm_start", _time.time())) * 1000
        prev["graph_time_ms"] = 0 # Built inline with LLM task for now
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

@celery_app.task(bind=True, max_retries=3)
def quality_validation_task(self, prev: dict):
    if not prev: return None
    logger.info(f"[DAG] quality_validation_task for {prev['job_id']}")
    db = SessionLocal()
    try:
        job, doc = get_job_and_doc(db, prev['job_id'], prev['tenant_id'], prev['document_id'])
        set_status_and_publish(db, doc, "quality_validation", prev['tenant_id'])
        
        from backend.db.postgres import Entity, EntityRelationship
        chunks_count = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        entities_count = db.query(Entity).filter(Entity.source_doc_id == doc.id).count()
        rels_count = db.query(EntityRelationship).filter(EntityRelationship.source_doc_id == doc.id).count()
        
        # Validation checks
        if chunks_count == 0:
            raise ValueError("Validation Failed: 0 chunks found in DB")
            
        metrics = {
            "chunks_count": chunks_count,
            "entities_count": entities_count,
            "relationships_count": rels_count,
        }
        
        from backend.db.postgres import ProcessingMetrics
        total_time_ms = (_time.time() - prev.get('start_time', _time.time())) * 1000
        metrics_record = ProcessingMetrics(
            document_id=doc.id,
            parse_time_ms=prev.get('parse_time_ms', 0),
            embed_time_ms=prev.get('embed_time_ms', 0),
            llm_time_ms=prev.get('llm_time_ms', 0),
            graph_time_ms=prev.get('graph_time_ms', 0),
            total_time_ms=total_time_ms
        )
        db.add(metrics_record)
        
        job.details = json.dumps(metrics)
        job.status = "completed"
        set_status_and_publish(db, doc, "completed", prev['tenant_id'])
        return prev
    except Exception as e:
        db.rollback()
        if 'job' in locals() and job: job.status = "failed"; job.error = str(e)
        if 'doc' in locals() and doc: set_status_and_publish(db, doc, "failed", prev['tenant_id'])
        raise self.retry(exc=e, countdown=5)
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3)
def delete_document_task(self, job_id: str, tenant_id: str, document_id: int, file_path: str):
    """
    Resilient background task to delete a document and all its derived artifacts.
    """
    start_time = _time.time()
    logger.info(f"START - Deletion task for job {job_id}, document {document_id} (Tenant: {tenant_id})")
    
    db = SessionLocal()
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id, ProcessingJob.tenant_id == tenant_id).first()
    
    if not job:
        logger.error(f"FAILURE - Deletion Job {job_id} not found.")
        db.close()
        return

    job.status = "deleting"
    db.commit()
    
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == tenant_id).first()
    if doc:
        doc.status = "deleting"
        db.commit()
        publish_document_status(doc, tenant_id)
    
    try:
        progress_tracker.init_job(job_id, 100)
        
        # 1. Database Cleanup (Flush but don't commit yet to allow rollback)
        progress_tracker.update_stage(job_id, "finalizing_database", 20)
        doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == tenant_id).first()
        filename = "Unknown Document"
        if doc:
            filename = doc.filename
            
            # Hard delete chunks and entities to free DB space
            db.query(Chunk).filter(Chunk.document_id == document_id).delete(synchronize_session=False)
            db.query(Entity).filter(Entity.source_doc_id == document_id).delete(synchronize_session=False)
            
            # Soft delete the document
            doc.status = "deleted"
            
            # Enriched Audit log without circular import
            audit = AuditLog(
                tenant_id=tenant_id,
                user_id=None,
                actor_type="WORKER",
                actor_name="system_worker",
                action="delete_document",
                query_text=filename,
                details=json.dumps({
                    "document_id": document_id, 
                    "document_name": filename,
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "reason": "User requested permanent deletion"
                })
            )
            db.add(audit)
            db.flush() # Hold the transaction open
            logger.info(f"Staged DB deletes for doc_id {document_id}")
        else:
            logger.warning(f"Document {document_id} not found in DB.")

        # 2. Qdrant Cleanup
        progress_tracker.update_stage(job_id, "deleting_vectors", 40)
        logger.info(f"Deleting vectors for doc_id {document_id}")
        qdrant_client.delete_by_doc_id(settings.QDRANT_COLLECTION_NAME, document_id, tenant_id=tenant_id)
        
        # 3. Neo4j Cleanup - Relationships
        progress_tracker.update_stage(job_id, "cleaning_graph_relationships", 60)
        logger.info(f"Deleting relationships for doc_id {document_id}")
        rel_query = """
        MATCH ()-[r]->() 
        WHERE r.source_doc_id = $doc_id AND r.tenant_id = $tenant_id 
        DELETE r
        """
        _neo4j_client.run_query(rel_query, {'doc_id': document_id, 'tenant_id': tenant_id})
        
        # 4. Neo4j Cleanup - Orphan Nodes (Scoped)
        progress_tracker.update_stage(job_id, "cleaning_graph_nodes", 80)
        logger.info(f"Deleting orphan nodes for doc_id {document_id} tenant {tenant_id}")
        node_query = """
        MATCH (n) 
        WHERE n.tenant_id = $tenant_id AND n.source_doc_id = $doc_id AND NOT (n)--() 
        DELETE n
        """
        _neo4j_client.run_query(node_query, {'doc_id': document_id, 'tenant_id': tenant_id})
        
        # DB Commit: commit DB changes now that external systems succeeded
        if doc:
            db.commit()
            publish_document_status(doc, tenant_id)
            
        # 5. File Cleanup (Absolute last step for debuggability)
        progress_tracker.update_stage(job_id, "removing_files", 90)
        if file_path and _sys_os.path.exists(file_path):
            try:
                _sys_os.remove(file_path)
                logger.info(f"Deleted file {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete file {file_path}: {e}")

        # Complete
        job.status = "completed"
        db.commit()
        progress_tracker.complete_job(job_id)
        time_taken = _time.time() - start_time
        logger.info(f"SUCCESS - Completed deletion job {job_id} | TIME TAKEN: {time_taken:.2f}s")
        
    except Exception as e:
        db.rollback()
        time_taken = _time.time() - start_time
        logger.error(f"FAILURE - Deletion task failed: {e} | TIME TAKEN: {time_taken:.2f}s", exc_info=True)
        job.status = "failed"
        job.error = str(e)
        db.commit()
        if 'doc' in locals() and doc:
            doc.status = "failed"
            db.commit()
            publish_document_status(doc, tenant_id)
        progress_tracker.fail_job(job_id, str(e))
        
        if "timeout" in str(e).lower() or "connection" in str(e).lower():
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
            
    finally:
        db.close()
