import logging
from typing import Dict, Any, List

from backend.tasks.celery_app import celery_app
from backend.tasks.progress_tracker import progress_tracker
from backend.db.postgres import SessionLocal, ProcessingJob, Document, Chunk
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
                "metadata": {"source_file": doc.filename}
            })
            
        qdrant_ids = qdrant_client.upsert_chunks(
            settings.QDRANT_COLLECTION_NAME, 
            qdrant_chunks,
            tenant_id=tenant_id
        )
        
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
            
        # Build Knowledge Graph
        logger.info(f"Upserting {len(all_entities)} entities and {len(all_relationships)} relationships")
        graph_stats = build_graph_from_extraction(all_entities, all_relationships, doc.id, tenant_id=tenant_id)
        
        # Complete
        job.status = "completed"
        doc.status = "completed"
        db.commit()
        
        progress_tracker.complete_job(job_id)
        logger.info(f"Successfully completed job {job_id}. Graph stats: {graph_stats}")
        
    except Exception as e:
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
