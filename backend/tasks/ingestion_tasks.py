import logging
import os as _sys_os
from typing import Dict, Any, List

from backend.tasks.celery_app import celery_app
from backend.tasks.progress_tracker import progress_tracker
from backend.db.postgres import SessionLocal, ProcessingJob, Document, Chunk, Entity
from backend.ingestion.document_processor import process_document
from backend.ingestion.entity_extractor import batch_extract_entities
from backend.graph.graph_builder import build_graph_from_extraction
from backend.vector.qdrant_client import qdrant_client
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

@celery_app.task(bind=True, max_retries=3)
def process_document_task(self, job_id: str, tenant_id: str):
    """
    Main Celery task to process a document: text extraction, chunking, 
    embedding, entity extraction, and graph building.
    """
    logger.info(f"Starting Celery task for job {job_id} (Tenant: {tenant_id})")
    
    db = SessionLocal()
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id, ProcessingJob.tenant_id == tenant_id).first()
    
    if not job:
        logger.error(f"Job {job_id} not found for tenant {tenant_id}")
        db.close()
        return

    job.status = "processing"
    db.commit()
    
    doc = db.query(Document).filter(Document.id == job.document_id, Document.tenant_id == tenant_id).first()
    if not doc:
        job.status = "failed"
        job.error = "Document not found"
        db.commit()
        db.close()
        return

    doc.status = "processing"
    db.commit()
    
    try:
        # 1. Extraction & Chunking
        progress_tracker.update_stage(job_id, "text_extraction", 10)
        chunks_data = process_document(
            file_path=doc.file_path,
            document_id=doc.id
        )
        
        if not chunks_data:
            raise ValueError("No text extracted from document")
            
        risk_chunks = [c for c in chunks_data if c.get("metadata", {}).get("has_risk_signal", False)]
        has_high_risk_content = len(risk_chunks) > 0
        section_types_found = list(set(c.get("metadata", {}).get("section_type", "general") for c in chunks_data))
        
        job.details = json.dumps({
            "risk_signals_found": len(risk_chunks),
            "has_high_risk_content": has_high_risk_content,
            "section_types_found": section_types_found
        })
        db.commit()
            
        progress_tracker.init_job(job_id, len(chunks_data))
        progress_tracker.update_stage(job_id, "vector_embedding", 20)
        
        # 2. Vector Database Upsert
        # Convert to Qdrant format
        qdrant_chunks = []
        for i, chunk in enumerate(chunks_data):
            qdrant_chunks.append({
                "text": chunk["text"],
                "doc_id": doc.id,
                "page": chunk["page_number"],
                "chunk_index": i,
                "section_type": chunk.get("metadata", {}).get("section_type", "general"),
                "has_risk_signal": chunk.get("metadata", {}).get("has_risk_signal", False),
                "metadata": {"source_file": doc.filename}
            })
            
        qdrant_ids = qdrant_client.upsert_chunks(
            settings.QDRANT_COLLECTION_NAME, 
            qdrant_chunks,
            tenant_id=tenant_id
        )
        
        # Verify Qdrant insertion
        logger.info(f"Inserted {len(qdrant_chunks)} chunks into Qdrant")
        
        progress_tracker.update_progress_with_metadata(job_id, "vector_embedding", 20, {"chunks_embedded": len(qdrant_chunks)})
        
        # Save chunks to Postgres
        for i, chunk in enumerate(chunks_data):
            db_chunk = Chunk(
                tenant_id=tenant_id,
                document_id=doc.id,
                page_number=chunk["page_number"],
                chunk_index=i,
                text_content=chunk["text"],
                qdrant_id=qdrant_ids[i]
            )
            db.add(db_chunk)
            
        db.commit()
        
        # 3. Entity Extraction & Graph Building
        progress_tracker.update_stage(job_id, "entity_extraction", 50)
        
        # Collect texts for batch extraction
        texts = [c["text"] for c in chunks_data]
        
        # Run extraction
        logger.info(f"Running entity extraction on {len(texts)} chunks for doc {doc.id}")
        extraction_results = batch_extract_entities(texts, tenant_id=tenant_id)
        
        progress_tracker.update_stage(job_id, "graph_building", 80)
        
        # Consolidate entities and relationships across chunks
        all_entities = []
        all_relationships = []
        for res in extraction_results:
            all_entities.extend(res.get("entities", []))
            all_relationships.extend(res.get("relationships", []))
            
        all_entities = [e for e in all_entities if e.get("confidence", 0.5) >= 0.35]
        all_relationships = [r for r in all_relationships if r.get("confidence", 0.5) >= 0.40]
        logger.info(f"After confidence filter: {len(all_entities)} entities, {len(all_relationships)} relationships")
        
        progress_tracker.update_progress_with_metadata(
            job_id, "entity_extraction", 50,
            {"entities_found": len(all_entities), "relationships_found": len(all_relationships)}
        )
            
        # SAVE ENTITIES TO POSTGRESQL (CRITICAL FIX)
        from backend.ingestion.entity_extractor import deduplicate_and_save_entities
        logger.info(f"Saving {len(all_entities)} extracted entities to Postgres.")
        deduplicate_and_save_entities(db, all_entities, doc.id, tenant_id)
        db.commit()

        # Publish events for live SSE frontend
        try:
            r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
            for ent in all_entities:
                r.publish(f"ingestion:{job_id}", json.dumps({
                    "event": "entity_created",
                    "data": {"id": ent["name"], "name": ent["name"], "label": ent["type"], "confidence": 1.0}
                }))
            for rel in all_relationships:
                r.publish(f"ingestion:{job_id}", json.dumps({
                    "event": "relationship_created",
                    "data": {"source": rel["source"], "target": rel["target"], "type": rel["type"], "confidence": 1.0}
                }))
        except Exception as pub_err:
            logger.warning(f"Failed to publish SSE events: {pub_err}")

            
        # Build Knowledge Graph
        logger.info(f"Upserting {len(all_entities)} entities and {len(all_relationships)} relationships")
        graph_stats = build_graph_from_extraction(all_entities, all_relationships, doc.id, tenant_id=tenant_id)
        
        progress_tracker.update_progress_with_metadata(
            job_id, "graph_building", 80,
            {"nodes_created": graph_stats.get("nodes_created", 0), "edges_created": graph_stats.get("relationships_created", 0)}
        )
        
        # Verify Neo4j insertion
        try:
            node_count = _neo4j_client.run_query("MATCH (n) RETURN count(n) as count")[0]["count"]
            logger.info(f"Verified Neo4j insertion: total graph nodes is now {node_count}")
        except Exception as e:
            logger.warning(f"Failed to verify Neo4j node count: {e}")
            
        # Complete
        job.status = "completed"
        doc.status = "completed"
        db.commit()
        
        progress_tracker.complete_job(job_id)
        logger.info(f"Successfully completed job {job_id}. Graph stats: {graph_stats}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Task failed: {e}", exc_info=True)
        job.status = "failed"
        job.error = str(e)
        doc.status = "failed"
        db.commit()
        progress_tracker.fail_job(job_id, str(e))
        
        # Retry with exponential backoff if it's an API/Connection error
        if "timeout" in str(e).lower() or "connection" in str(e).lower() or "50" in str(e):
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
            
    finally:
        db.close()

from backend.graph.neo4j_client import neo4j_client as _neo4j_client
from backend.db.postgres import AuditLog
import json as _json
import redis
import json

import time as _time

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
    
    try:
        progress_tracker.init_job(job_id, 100)
        
        # 1. Qdrant Cleanup
        progress_tracker.update_stage(job_id, "deleting_vectors", 20)
        logger.info(f"Deleting vectors for doc_id {document_id}")
        qdrant_client.delete_by_doc_id(settings.QDRANT_COLLECTION_NAME, document_id, tenant_id=tenant_id)
        
        # 2. Neo4j Cleanup - Relationships
        progress_tracker.update_stage(job_id, "cleaning_graph_relationships", 40)
        logger.info(f"Deleting relationships for doc_id {document_id}")
        rel_query = """
        MATCH ()-[r]->() 
        WHERE r.source_doc_id = $doc_id AND r.tenant_id = $tenant_id 
        DELETE r
        """
        _neo4j_client.run_query(rel_query, {'doc_id': document_id, 'tenant_id': tenant_id})
        
        # 3. Neo4j Cleanup - Orphan Nodes (Scoped)
        progress_tracker.update_stage(job_id, "cleaning_graph_nodes", 60)
        logger.info(f"Deleting orphan nodes for doc_id {document_id} tenant {tenant_id}")
        node_query = """
        MATCH (n) 
        WHERE n.tenant_id = $tenant_id AND n.source_doc_id = $doc_id AND NOT (n)--() 
        DELETE n
        """
        _neo4j_client.run_query(node_query, {'doc_id': document_id, 'tenant_id': tenant_id})
        
        # 4. Database Cleanup (Soft delete document, hard delete chunks/entities)
        progress_tracker.update_stage(job_id, "finalizing_database", 80)
        doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == tenant_id).first()
        if doc:
            filename = doc.filename
            
            # Hard delete chunks and entities to free DB space
            db.query(Chunk).filter(Chunk.document_id == document_id).delete()
            db.query(Entity).filter(Entity.source_doc_id == document_id).delete()
            
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
                details=_json.dumps({
                    "document_id": document_id, 
                    "document_name": filename,
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "reason": "User requested permanent deletion"
                })
            )
            db.add(audit)
            db.commit()
            logger.info(f"Soft deleted Document row and hard deleted chunks/entities for doc_id {document_id}")
        else:
            logger.warning(f"Document {document_id} not found in DB.")
            
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
        progress_tracker.fail_job(job_id, str(e))
        
        if "timeout" in str(e).lower() or "connection" in str(e).lower():
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
            
    finally:
        db.close()
