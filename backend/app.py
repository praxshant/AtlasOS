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
from backend.tasks.ingestion_tasks import process_document_task
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

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=6)
    role: Optional[str] = "engineer"

class UserLogin(BaseModel):
    username: str
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
    existing_user = db.query(User).filter((User.username == payload.username) | (User.email == payload.email)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered."
        )
    hashed = hash_password(payload.password)
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hashed,
        role=payload.role,
        tenant_id=settings.DEFAULT_TENANT_ID # Assign to default tenant if self-service
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Registered user: {user.username} with role: {user.role} for tenant: {user.tenant_id}")
    return {"message": "User registered successfully."}

@app.post("/api/auth/login", response_model=TokenResponse)
def login_user(
    payload: UserLogin, 
    db: Session = Depends(get_db),
    _ = Depends(anon_rate_limit(20, 60))
):
    user = db.query(User).filter(User.username == payload.username).first()
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
            action=action,
            query_text=query_text,
            details=json.dumps(details) if details else None
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

# --- File Ingestion Endpoints ---

@app.post("/api/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    source: str = Form("upload"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_role(["admin", "engineer"])),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(5, 60))
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

    # Push to Celery queue
    try:
        process_document_task.delay(job_id, tenant_id)
        logger.info(f"Dispatched Celery task for document job {job_id} (Tenant: {tenant_id})")
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
    chunk_count = db.query(Chunk).filter(Chunk.document_id == job.document_id).count()
    entity_count = db.query(Entity).filter(Entity.source_doc_id == job.document_id).count()

    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "filename": doc.filename if doc else "Unknown",
        "status": job.status,
        "error": job.error,
        "chunks_extracted": chunk_count,
        "entities_extracted": entity_count,
        "updated_at": job.updated_at
    }

@app.get("/api/jobs/{job_id}/progress")
def get_job_progress(
    job_id: str,
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Returns real-time granular progress for a Celery job from Redis."""
    return progress_tracker.get_progress(job_id)

@app.get("/api/documents")
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    docs = db.query(Document).filter(Document.tenant_id == tenant_id).order_by(Document.upload_time.desc()).all()
    return [{
        "id": d.id,
        "filename": d.filename,
        "file_type": d.file_type,
        "status": d.status,
        "upload_time": d.upload_time,
        "source": d.source
    } for d in docs]

# --- Stats & Graph Data Endpoints ---

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
    doc_count = db.query(Document).filter(Document.tenant_id == tenant_id).count()
    chunk_count = db.query(Chunk).filter(Chunk.tenant_id == tenant_id).count()
    entity_count = db.query(Entity).filter(Entity.tenant_id == tenant_id).count()

    # Query Neo4j stats
    node_count = 0
    edge_count = 0
    try:
        node_res = neo4j_client.run_query("MATCH (n) WHERE n.tenant_id = $tenant_id RETURN count(n) as count", {"tenant_id": tenant_id})
        if node_res:
            node_count = node_res[0]["count"]

        edge_res = neo4j_client.run_query("MATCH ()-[r]->() WHERE r.tenant_id = $tenant_id RETURN count(r) as count", {"tenant_id": tenant_id})
        if edge_res:
            edge_count = edge_res[0]["count"]
    except Exception as e:
        logger.warning(f"Could not connect to Neo4j to fetch stats: {e}")

    return {
        "documents": doc_count,
        "chunks": chunk_count,
        "entities": entity_count,
        "graph_nodes": node_count,
        "graph_edges": edge_count
    }

@app.get("/api/graph/data")
def get_graph_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Fetches Neo4j nodes and edges and formats them for force-directed graph rendering, scoped to tenant.
    """
    log_audit(db, current_user, "get_graph_data")
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

    nodes_dict = {}
    edges = []

    try:
        results = neo4j_client.run_query(query, {"tenant_id": tenant_id})
        orphans = neo4j_client.run_query(orphan_query, {"tenant_id": tenant_id})

        # Process connected nodes & edges
        for row in results:
            n_data = row["n"]
            n_label = row["n_labels"][0] if row["n_labels"] else "Entity"
            m_data = row["m"]
            m_label = row["m_labels"][0] if row["m_labels"] else "Entity"

            n_name = n_data.get("name")
            m_name = m_data.get("name")

            if n_name not in nodes_dict:
                nodes_dict[n_name] = {
                    "id": n_name,
                    "name": n_name,
                    "label": n_label,
                    "confidence": n_data.get("confidence", 1.0),
                    "properties": {k: v for k, v in n_data.items() if k not in ["name", "confidence", "source_doc_id"]}
                }

            if m_name not in nodes_dict:
                nodes_dict[m_name] = {
                    "id": m_name,
                    "name": m_name,
                    "label": m_label,
                    "confidence": m_data.get("confidence", 1.0),
                    "properties": {k: v for k, v in m_data.items() if k not in ["name", "confidence", "source_doc_id"]}
                }

            edges.append({
                "source": n_name,
                "target": m_name,
                "type": row["r_type"],
                "confidence": row["r"].get("confidence", 1.0)
            })

        # Process orphan nodes
        for row in orphans:
            n_data = row["n"]
            n_label = row["n_labels"][0] if row["n_labels"] else "Entity"
            n_name = n_data.get("name")

            if n_name not in nodes_dict:
                nodes_dict[n_name] = {
                    "id": n_name,
                    "name": n_name,
                    "label": n_label,
                    "confidence": n_data.get("confidence", 1.0),
                    "properties": {k: v for k, v in n_data.items() if k not in ["name", "confidence", "source_doc_id"]}
                }

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
            # Yield initial token indicating start
            yield "data: " + json.dumps({"status": "thinking"}) + "\n\n"
            
            # Request token generator from copilot
            token_generator = copilot_agent.run_stream(payload.query, payload.history, tenant_id=tenant_id)
            
            for token in token_generator:
                if isinstance(token, dict) and "citations" in token:
                    # Send citations metadata in a special channel block
                    yield "data: " + json.dumps({"citations": token["citations"]}) + "\n\n"
                elif isinstance(token, dict) and "graph" in token:
                    # Send matching Neo4j graph paths
                    yield "data: " + json.dumps({"graph": token["graph"]}) + "\n\n"
                else:
                    yield "data: " + json.dumps({"token": token}) + "\n\n"
                    
            yield "data: " + json.dumps({"status": "done"}) + "\n\n"
        except Exception as e:
            logger.exception("Error in copilot query streaming:")
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

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
    tenant graph. Items are sorted by coverage ascending (riskiest first).
    Gap nodes are simultaneously persisted to the graph for explorer visibility.
    """
    log_audit(db, current_user, "get_all_knowledge_gaps")
    try:
        gaps = neo4j_client.get_all_equipment_gaps(tenant_id=tenant_id)
        return {"gaps": gaps, "total_equipment": len(gaps)}
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


# --- Engineer Knowledge Preservation Endpoints ---

@app.get("/api/engineers")
def list_engineers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Returns all Person nodes (engineers) found in the tenant knowledge graph.
    """
    log_audit(db, current_user, "list_engineers")
    try:
        names = neo4j_client.get_all_engineers(tenant_id=tenant_id)
        return {"engineers": names, "total": len(names)}
    except Exception as e:
        logger.exception("Failed to list engineers:")
        raise HTTPException(status_code=500, detail=f"Failed to list engineers: {e}")


@app.get("/api/engineers/{engineer_name}/expertise")
def get_engineer_expertise(
    engineer_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Derives an engineer's expertise score, event breakdown, and equipment
    portfolio from graph traversal. No separate store — derived on demand.
    """
    log_audit(db, current_user, "get_engineer_expertise", engineer_name)
    try:
        expertise = neo4j_client.get_engineer_expertise(engineer_name, tenant_id=tenant_id)
        return expertise
    except Exception as e:
        logger.exception(f"Expertise derivation failed for {engineer_name}:")
        raise HTTPException(status_code=500, detail=f"Expertise derivation failed: {e}")


@app.get("/api/engineers/risk/{equipment_name}")
def get_knowledge_risk(
    equipment_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    _ = Depends(rate_limit(60, 60))
):
    """
    Returns retirement risk assessment for a specific piece of equipment,
    identifying concentration of knowledge in individual engineers.
    """
    log_audit(db, current_user, "get_knowledge_risk", equipment_name)
    try:
        risk = neo4j_client.get_knowledge_risk_by_equipment(equipment_name, tenant_id=tenant_id)
        return risk
    except Exception as e:
        logger.exception(f"Knowledge risk assessment failed for {equipment_name}:")
        raise HTTPException(status_code=500, detail=f"Knowledge risk assessment failed: {e}")

