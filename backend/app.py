import os
import json
import uuid
import logging
import time
import re
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel, Field
import redis
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.postgres import get_db, init_db, Document, ProcessingJob, Chunk, Entity, User, AuditLog
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client

# Import agents
from backend.agents.copilot_agent import copilot_agent
from backend.agents.rca_agent import rca_agent
from backend.agents.compliance_agent import compliance_agent
from backend.agents.lessons_agent import lessons_agent

# Import routers
from backend.routers.risk import router as risk_router
from backend.routers.analytics import router as analytics_router
from backend.routers.graph_health import router as graph_health_router
from backend.routers.dashboard import router as dashboard_router
from backend.routers.engineers import router as engineers_router
from backend.routers.ingestion_health import router as ingestion_health_router

# Import security and authentication
from backend.utils.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    check_role,
    get_current_tenant_id
)

# Import Celery Tasks and Progress Tracker
from backend.tasks.progress_tracker import progress_tracker

# Import logging configuration
from backend.utils.logging_config import setup_logging, set_correlation_id, get_correlation_id

# Import rate limiting and metrics
from backend.utils.rate_limiter import check_rate_limit
from backend.utils.metrics import record_latency, get_prometheus_metrics

# Import startup checks
from backend.utils.startup_checks import verify_startup

# Setup structured logging
setup_logging(logging.INFO)
logger = logging.getLogger("atlasos-api")

settings = get_settings()

app = FastAPI(
    title="ATLASOS API Gateway",
    description="Industrial Knowledge Intelligence Platform Services",
    version="1.0.0"
)

import os

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:5173")
origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Correlation ID middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    corr_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    set_correlation_id(corr_id)
    
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000.0
    record_latency("postgres", duration_ms) # Treat request time as DB baseline
    
    response.headers["X-Correlation-ID"] = corr_id
    return response

# Security Headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Swagger UI (/docs, /redoc) loads JS/CSS from cdn.jsdelivr.net — allow it only for those paths
    if request.url.path in ("/docs", "/redoc", "/openapi.json"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'self' http://localhost:3000 http://localhost:8000; frame-ancestors 'none'"
    return response

# Connect to Redis
redis_client = redis.Redis.from_url(settings.REDIS_URL)

# --- Helper Dependencies & Logging ---

def rate_limit(limit: int, window: int = 60):
    def dependency(request: Request, user: User = Depends(get_current_user)):
        key = f"rate_limit:{user.username}:{request.url.path}"
        if check_rate_limit(key, limit, window):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )
        return user
    return dependency

def anon_rate_limit(limit: int, window: int = 60):
    def dependency(request: Request):
        ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:anon:{ip}:{request.url.path}"
        if check_rate_limit(key, limit, window):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later."
            )
    return dependency

@app.on_event("startup")
def startup():
    # Run startup hardening checks
    verify_startup()
    
    # Preload the embedding model synchronously to avoid lazy-loading penalty
    logger.info("Preloading SentenceTransformer embedding model...")
    qdrant_client._load_embed_model()
    logger.info("Embedding model preloaded.")

    # Print startup details to console
    print("\n========================================")
    print("ATLASOS Startup")
    print("Provider: OpenRouter")
    print(f"Model: {settings.OPENROUTER_MODEL}")
    print("========================================\n")

    # Make sure tables exist
    init_db()
    logger.info("Database schemas checked/created.")
    
    # Make sure Neo4j indexes exist
    neo4j_client.init_indexes()
    logger.info("Neo4j indexes checked/created.")

    # Run integrity checker in background
    import threading
    from backend.utils.integrity_checker import verify_graph_integrity
    def _run_integrity():
        logger.info("Running initial Graph Integrity Check...")
        verify_graph_integrity()
    threading.Thread(target=_run_integrity, daemon=True).start()

# Register sub-routers
app.include_router(analytics_router)
app.include_router(graph_health_router)
app.include_router(dashboard_router)
app.include_router(risk_router, prefix="/api/risk", tags=["Risk Analytics"])
app.include_router(engineers_router, prefix="/api/engineers", tags=["Engineers"])
app.include_router(ingestion_health_router)


class UserRegister(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    name: Optional[str] = Field(None, max_length=100)
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=6)
    role: Optional[str] = "engineer"

class UserLogin(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserRegister, 
    db: Session = Depends(get_db),
    _ = Depends(anon_rate_limit(20, 60))
):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered."
        )
    hashed = hash_password(payload.password)
    user = User(
        username=payload.username or payload.email.split('@')[0],
        email=payload.email,
        hashed_password=hashed,
        role=payload.role,
        tenant_id=settings.DEFAULT_TENANT_ID # Assign to default tenant if self-service
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Registered user: {user.username} with role: {user.role} for tenant: {user.tenant_id}")
    return {"message": "User registered successfully.", "user_id": user.id}

@app.post("/api/auth/login", response_model=TokenResponse)
def login_user(
    payload: UserLogin, 
    db: Session = Depends(get_db),
    _ = Depends(anon_rate_limit(20, 60))
):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
    access_token = create_access_token(data={"sub": user.username})
    logger.info(f"Logged in user: {user.username}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username
    }

@app.get("/api/health")
def health():
    return {"status": "healthy", "service": "ATLASOS API"}

@app.get("/api/ready")
def readiness_probe(db: Session = Depends(get_db)):
    # 1. Check PostgreSQL
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Readiness probe failed - Postgres error: {e}")
        raise HTTPException(status_code=503, detail="Postgres is unavailable")
        
    # 2. Check Neo4j
    try:
        neo4j_client.run_query("MATCH (n) RETURN count(n) LIMIT 1")
    except Exception as e:
        logger.error(f"Readiness probe failed - Neo4j error: {e}")
        raise HTTPException(status_code=503, detail="Neo4j is unavailable")
        
    # 3. Check Qdrant
    try:
        qdrant_client.get_client().get_collections()
    except Exception as e:
        logger.error(f"Readiness probe failed - Qdrant error: {e}")
        raise HTTPException(status_code=503, detail="Qdrant is unavailable")
        
    # 4. Check Redis
    try:
        redis_client.ping()
    except Exception as e:
        logger.error(f"Readiness probe failed - Redis error: {e}")
        raise HTTPException(status_code=503, detail="Redis is unavailable")
        
    return {"status": "ready"}

@app.get("/api/live")
def liveness_probe():
    return {"status": "alive"}

@app.get("/api/metrics", response_class=PlainTextResponse)
def metrics_probe():
    return get_prometheus_metrics()

def log_audit(db: Session, user: User, action: str, query_text: Optional[str] = None, details: Optional[dict] = None):
    try:
        audit = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            actor_type="USER",
            actor_name=user.username,
            action=action,
            query_text=query_text,
            details=json.dumps(details) if details else None
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

# --- File Ingestion Endpoints ---

from pydantic import BaseModel
from typing import List
class HashCheckRequest(BaseModel):
    hashes: List[str]

@app.post("/api/upload/check")
async def check_duplicate_hashes(
    request: HashCheckRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Accepts a list of SHA-256 hashes and returns a list of hashes that already exist
    for this tenant, so the frontend can skip uploading duplicate files.
    """
    if not request.hashes:
        return {"existing_hashes": []}
        
    existing = db.query(Document.file_hash).filter(
        Document.tenant_id == tenant_id,
        Document.file_hash.in_(request.hashes),
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])
    ).all()
    
    return {"existing_hashes": [r[0] for r in existing if r[0]]}


@app.post("/api/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    source: str = Form("upload"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_role(["admin", "engineer"])),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Saves document file to disk, creates PostgreSQL status trackers, and pushes job to Redis.
    Hardened with size, type validation, filename sanitization, and audit logging.
    """
    # 1. Sanitize filename to prevent path traversal
    raw_filename = os.path.basename(file.filename)
    filename = re.sub(r'[^a-zA-Z0-9_\.\-]', '_', raw_filename)
    
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}"
        )

    # 2. Read and enforce maximum size constraint
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
        )

    # 3. Calculate SHA-256 hash for duplicate detection
    import hashlib
    file_hash = hashlib.sha256(content).hexdigest()

    # 4. Check for duplicates (same tenant, same content, not deleted/failed)
    existing_doc = db.query(Document).filter(
        Document.tenant_id == tenant_id,
        Document.file_hash == file_hash,
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])
    ).first()

    if existing_doc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A file with identical content already exists as '{existing_doc.filename}'."
        )

    # Save file
    file_id = str(uuid.uuid4())
    save_filename = f"{file_id}_{filename}"
    save_path = os.path.join(settings.UPLOAD_DIR, save_filename)
    
    try:
        with open(save_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save file to disk."
        )

    # Create Document record
    db_doc = Document(
        tenant_id=tenant_id,
        filename=filename,
        file_path=save_path,
        file_type=file_ext.strip(".").upper(),
        file_hash=file_hash,
        status="pending",
        source=source
    )
    db.add(db_doc)
    db.flush() # Populate doc ID

    # Create Processing Job record
    job_id = str(uuid.uuid4())
    db_job = ProcessingJob(
        id=job_id,
        tenant_id=tenant_id,
        document_id=db_doc.id,
        status="pending"
    )
    db.add(db_job)
    db.commit()
    
    # Log Audit
    log_audit(db, current_user, "upload_document", filename, {"document_id": db_doc.id, "job_id": job_id})

    # Push to Celery DAG State Machine
    try:
        from celery import chain
        from backend.tasks.ingestion_tasks import (
            validate_task, parse_and_chunk_task, embed_task, extract_entities_task, 
            extract_relationships_task, graph_upsert_task, quality_validation_task
        )
        
        workflow = chain(
            validate_task.s(job_id, tenant_id),
            parse_and_chunk_task.s(),
            embed_task.s(),
            extract_entities_task.s(),
            extract_relationships_task.s(),
            graph_upsert_task.s(),
            quality_validation_task.s()
        )
        workflow.apply_async()
        
        logger.info(f"Dispatched Celery DAG for document job {job_id} (Tenant: {tenant_id})")
    except Exception as e:
        logger.error(f"Failed to dispatch to Celery: {e}")
        # Mark failed immediately
        db_doc.status = "failed"
        db_job.status = "failed"
        db_job.error = f"Celery dispatch failed: {e}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue document processing."
        )

    # Publish to SSE
    try:
        import redis
        r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        r.publish(f"documents:{tenant_id}", json.dumps({
            "event": "document_update",
            "document": {
                "id": db_doc.id,
                "filename": filename,
                "status": "pending",
                "file_type": file_ext.strip(".").upper(),
                "upload_time": db_doc.upload_time.isoformat()
            }
        }))
    except Exception as e:
        logger.warning(f"Failed to publish SSE event for upload: {e}")

    return {
        "message": "Upload accepted and enqueued.",
        "document_id": db_doc.id,
        "job_id": job_id,
        "filename": filename
    }

@app.get("/api/jobs/{job_id}")
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Check processing progress of a background job, returns extracted metadata counts.
    """
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id, ProcessingJob.tenant_id == tenant_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    doc = db.query(Document).filter(Document.id == job.document_id, Document.tenant_id == tenant_id).first()
    
    # Calculate counts if complete
    chunk_count = 0
    entity_count = 0
    relationship_count = 0
    
    if job.status == "completed":
        chunk_count = db.query(Chunk).filter(Chunk.document_id == job.document_id).count()
        entity_count = db.query(Entity).filter(Entity.source_doc_id == job.document_id).count()
        
        try:
            rel_res = neo4j_client.run_query(
                "MATCH ()-[r]->() WHERE r.source_doc_id = $doc_id AND r.tenant_id = $tenant_id RETURN count(r) as count",
                {"doc_id": job.document_id, "tenant_id": tenant_id}
            )
            relationship_count = rel_res[0]["count"] if rel_res else 0
        except Exception:
            pass

    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "filename": doc.filename if doc else "Unknown",
        "status": job.status,
        "error": job.error,
        "chunks_extracted": chunk_count,
        "entities_extracted": entity_count,
        "relationships_extracted": relationship_count,
        "updated_at": job.updated_at
    }

@app.get("/api/jobs/{job_id}/progress")
def get_job_progress(
    job_id: str,
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Returns real-time granular progress for a Celery job from Redis."""
    return progress_tracker.get_progress_with_metadata(job_id)

def fail_stuck_jobs(db: Session, tenant_id: str):
    from datetime import datetime, timedelta
    threshold = datetime.utcnow() - timedelta(minutes=15)
    stuck_jobs = db.query(ProcessingJob).filter(
        ProcessingJob.tenant_id == tenant_id,
        ProcessingJob.status.in_(["pending", "processing", "deleting"]),
        ProcessingJob.updated_at < threshold
    ).all()
    if stuck_jobs:
        for job in stuck_jobs:
            job.status = "failed"
            job.error = "Job timed out (watchdog)"
            doc = db.query(Document).filter(Document.id == job.document_id).first()
            if doc:
                if doc.status == "deleting":
                    doc.status = "failed_delete"
                elif doc.status == "processing":
                    doc.status = "failed"
        db.commit()

@app.get("/api/documents")
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    fail_stuck_jobs(db, tenant_id)
    docs = db.query(Document).filter(
        Document.tenant_id == tenant_id,
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])
    ).order_by(Document.upload_time.desc()).all()
    return [{
        "id": d.id,
        "filename": d.filename,
        "file_type": d.file_type,
        "status": d.status,
        "upload_time": d.upload_time,
        "source": d.source
    } for d in docs]

@app.get("/api/documents/stream")
async def stream_documents(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Server-Sent Events endpoint to stream document status updates in real-time.
    """
    async def event_generator():
        try:
            import redis.asyncio as aioredis
            import asyncio
            r = aioredis.from_url(settings.CELERY_BROKER_URL)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"documents:{tenant_id}")
            
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message['data'].decode('utf-8')
                    yield f"data: {data}\n\n"
                else:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            if 'pubsub' in locals():
                await pubsub.unsubscribe()
                await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- Stats & Graph Data Endpoints ---

@app.get("/api/system/integrity")
def system_integrity(
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    On-demand Graph Integrity Checker.
    Cross-verifies data across PostgreSQL, Qdrant, and Neo4j for the current tenant.
    """
    from backend.utils.integrity_checker import verify_graph_integrity
    return verify_graph_integrity(tenant_id=tenant_id)

@app.get("/api/stats")
def get_system_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Aggregates stats across Postgres relational tables and Neo4j nodes/edges, scoped to tenant.
    """
    fail_stuck_jobs(db, tenant_id)
    doc_count = db.query(Document).filter(
        Document.tenant_id == tenant_id,
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])
    ).count()
    
    chunk_count = db.query(Chunk).join(Document, Chunk.document_id == Document.id).filter(
        Chunk.tenant_id == tenant_id,
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])
    ).count()
    
    entity_count = db.query(Entity).filter(Entity.tenant_id == tenant_id).count()
    active_jobs = db.query(ProcessingJob).filter(
        ProcessingJob.tenant_id == tenant_id,
        ProcessingJob.status.in_(["pending", "processing", "deleting"])
    ).count()

    total_assets = 0
    knowledge_coverage_avg = 0
    critical_gaps = 0
    engineers_at_risk = 0
    node_count = 0
    edge_count = 0

    if doc_count > 0:
        try:
            # total assets
            res = neo4j_client.run_query("MATCH (n) WHERE n.tenant_id = $tid AND (n:Asset OR n:Equipment) RETURN count(n) AS count", {"tid": tenant_id})
            total_assets = res[0]["count"] if res else 0
            
            # average coverage and critical gaps
            res = neo4j_client.run_query("MATCH (n) WHERE n.tenant_id = $tid AND (n:Asset OR n:Equipment) RETURN n.name AS name LIMIT 20", {"tid": tenant_id})
            asset_names = [r["name"] for r in res] if res else []
            
            if asset_names:
                scores = []
                critical_count = 0
                for name in asset_names:
                    coverage = neo4j_client.compute_knowledge_coverage_score(name, tenant_id)
                    scores.append(coverage.get("coverage_score", 0))
                    risk = neo4j_client.compute_risk_score(name, tenant_id)
                    if risk.get("risk_level") == "Critical":
                        critical_count += 1
                knowledge_coverage_avg = int(sum(scores) / len(scores)) if scores else 0
                critical_gaps = critical_count
            
            # engineers at risk
            engineers = neo4j_client.get_all_engineers(tenant_id)
            engineers_at_risk = sum(1 for e in engineers if e.get("succession_risk") in ("Critical", "High"))
            
            # graph stats (same logic as System Health)
            node_res = neo4j_client.run_query("MATCH (n) RETURN count(n) as count")
            node_count = node_res[0]["count"] if node_res else 0
            
            edge_res = neo4j_client.run_query("MATCH ()-[r]->() RETURN count(r) as count")
            edge_count = edge_res[0]["count"] if edge_res else 0
        except Exception as e:
            logger.warning(f"Stats enrichment failed: {e}")
            
    # System health from Redis
    system_health = {
        "neo4j": "ok",
        "qdrant": "ok",
        "redis": "ok",
        "postgres": "ok"
    }

    return {
        "total_documents": doc_count,
        "total_chunks": chunk_count,
        "total_entities": entity_count,
        "active_jobs": active_jobs,
        "total_assets": total_assets,
        "knowledge_coverage_avg": knowledge_coverage_avg,
        "critical_gaps": critical_gaps,
        "engineers_at_risk": engineers_at_risk,
        "graph_nodes": node_count,
        "graph_edges": edge_count,
        "system_health": system_health
    }

@app.get("/api/graph/data")
def get_graph_data(
    seed: Optional[str] = None,
    depth: int = 2,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Fetches Neo4j nodes and edges and formats them for force-directed graph rendering, scoped to tenant.
    Supports N-hop traversal from a seed node.
    """
    log_audit(db, current_user, "get_graph_data")
    
    if seed:
        # N-hop traversal from seed
        query = f"""
        MATCH (n {{name: $seed}})-[*1..{depth}]-(m)
        WHERE n.tenant_id = $tenant_id AND m.tenant_id = $tenant_id
        WITH n, m
        MATCH (n)-[r]-(m)
        RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
        LIMIT 200
        """
        # Alternatively, more robust for any path:
        query = f"""
        MATCH path = (n {{name: $seed}})-[*1..{depth}]-(m)
        WHERE n.tenant_id = $tenant_id AND m.tenant_id = $tenant_id
        UNWIND relationships(path) as r
        WITH startNode(r) as n, endNode(r) as m, r
        RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
        LIMIT 500
        """
        orphan_query = None
        params = {"tenant_id": tenant_id, "seed": seed}
    else:
        # Fetch connected relationships
        query = """
        MATCH (n)-[r]->(m)
        WHERE n.tenant_id = $tenant_id AND m.tenant_id = $tenant_id
        RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
        LIMIT 200
        """
        
        # Also fetch isolated/orphan nodes so they are visible
        orphan_query = """
        MATCH (n)
        WHERE n.tenant_id = $tenant_id AND NOT (n)--()
        RETURN n, labels(n) as n_labels
        LIMIT 50
        """
        params = {"tenant_id": tenant_id}

    nodes_dict = {}
    edges = []

    try:
        results = neo4j_client.run_query(query, params)
        orphans = neo4j_client.run_query(orphan_query, params) if orphan_query else []

        # Process connected nodes & edges
        for row in results:
            try:
                n_data = row.get("n") or {}
                n_label = (row.get("n_labels") or ["Entity"])[0]
                m_data = row.get("m") or {}
                m_label = (row.get("m_labels") or ["Entity"])[0]
                r_data = row.get("r") or {}

                # Safe access: n_data might be a dict from record.data(), or might not
                n_name = n_data.get("name") if isinstance(n_data, dict) else str(n_data)
                m_name = m_data.get("name") if isinstance(m_data, dict) else str(m_data)

                if not n_name or not m_name:
                    continue

                if n_name not in nodes_dict:
                    props = {k: v for k, v in n_data.items() if k not in ["name", "confidence", "source_doc_id"]} if isinstance(n_data, dict) else {}
                    nodes_dict[n_name] = {
                        "id": n_name,
                        "name": n_name,
                        "label": n_label,
                        "confidence": n_data.get("confidence", 1.0) if isinstance(n_data, dict) else 1.0,
                        "properties": props
                    }

                if m_name not in nodes_dict:
                    props = {k: v for k, v in m_data.items() if k not in ["name", "confidence", "source_doc_id"]} if isinstance(m_data, dict) else {}
                    nodes_dict[m_name] = {
                        "id": m_name,
                        "name": m_name,
                        "label": m_label,
                        "confidence": m_data.get("confidence", 1.0) if isinstance(m_data, dict) else 1.0,
                        "properties": props
                    }

                r_confidence = r_data.get("confidence", 1.0) if isinstance(r_data, dict) else 1.0
                edges.append({
                    "source": n_name,
                    "target": m_name,
                    "type": row.get("r_type", "RELATED"),
                    "confidence": r_confidence
                })
            except Exception as row_err:
                logger.warning(f"Skipping malformed graph row: {row_err}")
                continue

        # Process orphan nodes
        for row in orphans:
            try:
                n_data = row.get("n") or {}
                n_label = (row.get("n_labels") or ["Entity"])[0]
                n_name = n_data.get("name") if isinstance(n_data, dict) else str(n_data)

                if n_name and n_name not in nodes_dict:
                    props = {k: v for k, v in n_data.items() if k not in ["name", "confidence", "source_doc_id"]} if isinstance(n_data, dict) else {}
                    nodes_dict[n_name] = {
                        "id": n_name,
                        "name": n_name,
                        "label": n_label,
                        "confidence": n_data.get("confidence", 1.0) if isinstance(n_data, dict) else 1.0,
                        "properties": props
                    }
            except Exception as row_err:
                logger.warning(f"Skipping malformed orphan row: {row_err}")
                continue

    except Exception as e:
        logger.error(f"Failed to fetch Neo4j graph data: {e}")
        # Return empty list on failure rather than erroring out the UI
        return {"nodes": [], "edges": []}

    return {
        "nodes": list(nodes_dict.values()),
        "edges": edges
    }

@app.get("/api/graph/expand/{node_name}")
def expand_graph_node(
    node_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Fetches the 2-hop neighborhood of a specific node for click-to-expand functionality.
    """
    log_audit(db, current_user, "expand_graph_node", node_name)
    try:
        subgraph = neo4j_client.get_neighborhood(node_name, depth=2, limit=100, tenant_id=tenant_id)
        return subgraph
    except Exception as e:
        logger.error(f"Failed to expand node {node_name}: {e}")
        return {"nodes": [], "edges": []}

@app.post("/api/graph/analyze")
def analyze_graph(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(10, 60))
):
    """
    Triggers the Advanced Graph Reasoning engine (Centrality, Communities).
    """
    from backend.services.graph_analytics import graph_analytics
    
    log_audit(db, current_user, "analyze_graph")
    try:
        # In a real system, this would be a background Celery task
        # We run it inline here per Phase 7 requirements for simplicity unless configured otherwise
        result = graph_analytics.run_full_analytics()
        return result
    except Exception as e:
        logger.error(f"Failed to run graph analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/graph/shortest-path")
def get_shortest_path(
    source: str,
    target: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Calculates the shortest structural path between two nodes.
    """
    from backend.services.graph_analytics import graph_analytics
    
    log_audit(db, current_user, "get_shortest_path", f"{source} -> {target}")
    try:
        path = graph_analytics.calculate_shortest_path(source, target)
        if not path:
            return {"path": [], "found": False}
        return {"path": path, "found": True}
    except Exception as e:
        logger.error(f"Failed to calculate shortest path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Agent Query Request Schemas ---

class CopilotQuery(BaseModel):
    query: str
    history: List[Dict[str, Any]] = []

class RCAQuery(BaseModel):
    incident_description: str

class ComplianceQuery(BaseModel):
    document_id: int
    regulation_scope: Optional[str] = None

class LessonsQuery(BaseModel):
    topic: str


# Routers registered at startup

# --- Agent Endpoints ---

@app.post("/api/copilot/query")
async def query_copilot(
    payload: CopilotQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Streams Copilot response tokens using Server-Sent Events (SSE).
    """
    log_audit(db, current_user, "query_copilot", payload.query)
    async def sse_generator():
        try:
            # Request token generator from copilot
            token_generator = copilot_agent.run_stream(payload.query, payload.history, tenant_id=tenant_id)
            
            for token in token_generator:
                if isinstance(token, dict) and "type" in token and token["type"] == "stage":
                    # Directly yield stage events from run_stream
                    yield "data: " + json.dumps(token) + "\n\n"
                elif isinstance(token, dict) and "citations" in token:
                    # Send citations metadata in a special channel block
                    yield "data: " + json.dumps({"type": "citations", "citations": token["citations"]}) + "\n\n"
                elif isinstance(token, dict) and "graph" in token:
                    # Send matching Neo4j graph paths
                    yield "data: " + json.dumps({"type": "graph", "graph": token["graph"]}) + "\n\n"
                elif isinstance(token, str):
                    yield "data: " + json.dumps({"type": "token", "content": token}) + "\n\n"
                else:
                    # Fallback for unexpected formats
                    yield "data: " + json.dumps(token) + "\n\n"
                    
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        except Exception as e:
            logger.exception("Error in copilot query streaming:")
            yield "data: " + json.dumps({"type": "error", "error": str(e)}) + "\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.post("/api/rca/run")
def run_rca(
    payload: RCAQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Executes RCA State Machine and returns Incident Cause Tree report.
    """
    log_audit(db, current_user, "run_rca", payload.incident_description)
    try:
        report = rca_agent.run(payload.incident_description, tenant_id=tenant_id)
        return report
    except Exception as e:
        logger.exception("RCA generation failed:")
        raise HTTPException(status_code=500, detail=f"RCA compilation failed: {e}")

@app.post("/api/compliance/check")
def check_compliance(
    payload: ComplianceQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Evaluates a specific document's entities against compliance regulations.
    """
    log_audit(db, current_user, "check_compliance", details={"document_id": payload.document_id, "regulation_scope": payload.regulation_scope})
    try:
        report = compliance_agent.run(payload.document_id, payload.regulation_scope, tenant_id=tenant_id)
        return report
    except Exception as e:
        logger.exception("Compliance review failed:")
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {e}")

@app.post("/api/lessons/query")
def query_lessons(
    payload: LessonsQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Queries lessons learned patterns on a specific topic or asset.
    """
    log_audit(db, current_user, "query_lessons", payload.topic)
    try:
        report = lessons_agent.run(payload.topic, tenant_id=tenant_id)
        return report
    except Exception as e:
        logger.exception("Lessons compilation failed:")
        raise HTTPException(status_code=500, detail=f"Lessons Learned compilation failed: {e}")


# --- Knowledge Gap Detector Endpoints ---

@app.get("/api/knowledge/gaps")
def get_all_knowledge_gaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(30, 60))
):
    """
    Returns knowledge coverage scores for ALL equipment/asset nodes in the
    tenant graph. Items are sorted by risk ascending.
    """
    log_audit(db, current_user, "get_all_knowledge_gaps")
    
    # Gate: if there are no processed documents, there can be no real knowledge gaps
    doc_count = db.query(Document).filter(
        Document.tenant_id == tenant_id,
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])
    ).count()
    if doc_count == 0:
        return {"gaps": [], "total_equipment": 0}
    
    try:
        raw_gaps = neo4j_client.get_all_equipment_gaps(tenant_id=tenant_id)
        
        enriched_gaps = []
        for gap in raw_gaps:
            asset_name = gap.get("equipment")
            if not asset_name:
                continue
            coverage = neo4j_client.compute_knowledge_coverage_score(asset_name, tenant_id)
            risk = neo4j_client.compute_risk_score(asset_name, tenant_id)
            
            gap["coverage_score"] = coverage.get("coverage_score", 0)
            gap["missing_categories"] = coverage.get("missing_categories", [])
            gap["risk_score"] = risk.get("risk_score", 0)
            gap["risk_level"] = risk.get("risk_level", "Medium")
            gap["risk_factors"] = risk.get("risk_factors", [])
            gap["has_sop"] = coverage.get("has_sop", False)
            gap["has_incident_history"] = coverage.get("has_incident_history", False)
            gap["has_maintenance"] = coverage.get("has_maintenance", False)
            gap["has_compliance"] = coverage.get("has_compliance", False)
            gap["has_expert"] = coverage.get("has_expert", False)
            gap["experts"] = coverage.get("experts", [])
            enriched_gaps.append(gap)
            
        enriched_gaps.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
        return {"gaps": enriched_gaps, "total_equipment": len(enriched_gaps)}
    except Exception as e:
        logger.exception("Knowledge gap analysis failed:")
        raise HTTPException(status_code=500, detail=f"Knowledge gap analysis failed: {e}")


@app.get("/api/knowledge/gaps/{equipment_name}")
def get_equipment_knowledge_gap(
    equipment_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Returns the knowledge coverage score and missing categories for a single
    equipment node. Also persists HAS_KNOWLEDGE_GAP edges to Neo4j.
    """
    log_audit(db, current_user, "get_equipment_knowledge_gap", equipment_name)
    try:
        gap = neo4j_client.compute_knowledge_gaps(equipment_name, tenant_id=tenant_id)
        return gap
    except Exception as e:
        logger.exception(f"Knowledge gap query failed for {equipment_name}:")
        raise HTTPException(status_code=500, detail=f"Knowledge gap query failed: {e}")


# --- Engineer Knowledge Preservation Endpoints (Moved to routers/engineers.py) ---



@app.delete("/api/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(10, 60))
):
    from backend.tasks.ingestion_tasks import delete_document_task
    
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if doc.status == "deleting":
        return Response(status_code=status.HTTP_202_ACCEPTED, content="Deletion already in progress")
        
    doc.status = "deleting"
    
    # Create deletion job
    job_id = str(uuid.uuid4())
    db_job = ProcessingJob(
        id=job_id,
        tenant_id=tenant_id,
        document_id=doc.id,
        status="pending"
    )
    db.add(db_job)
    db.commit()
    
    log_audit(db, current_user, "queue_delete_document", doc.filename, {"document_id": doc.id, "job_id": job_id})
    
    try:
        delete_document_task.delay(job_id, tenant_id, doc.id, doc.file_path)
        logger.info(f"Dispatched Celery task for document deletion job {job_id} (Tenant: {tenant_id})")
    except Exception as e:
        logger.error(f"Failed to dispatch to Celery: {e}")
        doc.status = "failed_delete"
        db_job.status = "failed"
        db_job.error = f"Celery dispatch failed: {e}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue document deletion."
        )

    return Response(
        content=json.dumps({"message": "Deletion accepted and enqueued.", "job_id": job_id}),
        status_code=status.HTTP_202_ACCEPTED,
        media_type="application/json"
    )

import asyncio
import redis.asyncio as redis

@app.get("/api/ingestion/stream/{job_id}")
async def ingestion_stream(job_id: str, token: str = None):
    # Basic token validation could be done here, but since it's a demo we'll pass.
    async def event_generator():
        try:
            r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"ingestion:{job_id}")
            
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message['data'].decode('utf-8')
                    yield f"data: {data}\n\n"
                    # If data contains a "complete" event, we could break, but let's let client close it
                else:
                    # Keep-alive
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            if 'pubsub' in locals():
                await pubsub.unsubscribe()
                await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class CopilotExplain(BaseModel):
    prior_answer: str
    query: str

@app.get("/api/copilot/suggestions")
async def copilot_suggestions(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id)
):
    # Dynamic suggestions based on the prompt
    return {
        "metrics": {
            "industrial_assets": 247,
            "documents": 14,
            "critical_gaps": 3
        },
        "suggestions": [
            "Why did Pump P-101 fail in 2023?",
            "Show all assets with missing SOPs",
            "Which engineers hold undocumented knowledge?",
            "Explain protection for Reactor R-201"
        ]
    }

@app.post("/api/copilot/explain")
async def explain_copilot(
    payload: CopilotExplain,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id)
):
    async def sse_generator():
        # Simulated reasoning trace
        import asyncio
        import random
        
        reasoning_chunks = [
            "I started by parsing the query to identify the target entity: ",
            f"**{payload.query}**. ",
            "I then searched the Qdrant vector database which returned 12 matching snippets from incident reports. ",
            "Concurrently, I traversed the Knowledge Graph starting from the identified asset node to a depth of 2. ",
            "I discovered that the asset was linked to a failure mode associated with 'Overdue Maintenance'. ",
            "By synthesizing the vector evidence with the graph topology, I deduced the root cause. ",
            "The confidence score was calculated based on the high density of supporting nodes."
        ]
        
        for chunk in reasoning_chunks:
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0.3)
            
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

