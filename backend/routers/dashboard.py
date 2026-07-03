from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.db.postgres import get_db, User, AuditLog, Document, ProcessingJob
from backend.utils.auth import get_current_user, get_current_tenant_id
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client
from fastapi.responses import StreamingResponse
import json
import asyncio
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/api/dashboard/metrics")
def get_dashboard_metrics(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id)
):
    try:
        from backend.services.knowledge_service import get_system_metrics
        return get_system_metrics(db, tenant_id=tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/dashboard/activity")
def get_dashboard_activity(limit: int = 10, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_tenant_id)):
    logs = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    results = []
    for log in logs:
        severity = "info"
        title = log.action.replace("_", " ").title()
        detail = log.query_text or ""
        
        if log.action == "delete_document" or log.action == "queue_delete_document":
            severity = "warning"
            title = "Document Deleted"
            try:
                if log.details:
                    dt = json.loads(log.details)
                    if "document_name" in dt:
                        detail = dt["document_name"]
                    elif "document_id" in dt:
                        detail = f"Doc ID {dt['document_id']}"
            except:
                pass
        
        if log.action == "upload_document":
            severity = "info"
            title = "Document Uploaded"
            try:
                if log.details:
                    dt = json.loads(log.details)
                    if "filename" in dt:
                        detail = dt["filename"]
            except:
                pass

        results.append({
            "id": f"evt-{log.id}",
            "type": log.action,
            "timestamp": log.timestamp.isoformat() + "Z" if log.timestamp else "",
            "title": title,
            "detail": detail,
            "severity": severity
        })
    return results

@router.get("/api/system/health")
def get_system_health(db: Session = Depends(get_db)):
    try:
        nodes_res = neo4j_client.run_query("MATCH (n) RETURN count(n) as c")
        edges_res = neo4j_client.run_query("MATCH ()-[r]->() RETURN count(r) as c")
        nodes = nodes_res[0]["c"] if nodes_res else 0
        edges = edges_res[0]["c"] if edges_res else 0
        neo4j_status = "ok"
    except:
        nodes = edges = 0
        neo4j_status = "error"
        
    try:
        from backend.config import get_settings
        settings = get_settings()
        info = qdrant_client.get_client().get_collection(settings.QDRANT_COLLECTION_NAME)
        vectors = info.points_count
        qdrant_status = "ok"
    except:
        vectors = 0
        qdrant_status = "error"
        
    try:
        documents = db.query(Document).filter(Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])).count()
        pg_status = "ok"
    except:
        documents = 0
        pg_status = "error"
        
    return {
        "neo4j": {"status": neo4j_status, "nodes": nodes, "edges": edges},
        "qdrant": {"status": qdrant_status, "vectors": vectors},
        "redis": {"status": "ok", "queued_jobs": 0},
        "postgresql": {"status": pg_status, "documents": documents}
    }

@router.get("/api/dashboard")
def get_dashboard_full(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Single Source of Truth for the Dashboard"""
    metrics = get_dashboard_metrics(db=db, tenant_id=tenant_id)
    activity = get_dashboard_activity(limit=8, db=db, tenant_id=tenant_id)
    health = get_system_health(db=db)
    
    return {
        "metrics": metrics,
        "activity": activity,
        "health": health
    }

@router.get("/api/copilot/suggestions")
def get_copilot_suggestions(tenant_id: str = Depends(get_current_tenant_id)):
    """
    Returns suggested Copilot questions dynamically generated from the
    top connected nodes in the tenant's knowledge graph.
    Falls back to generic industrial questions when the graph is empty.
    """
    FALLBACK_SUGGESTIONS = [
        "What documents have been uploaded?",
        "Show all known assets",
        "What knowledge gaps exist in this facility?",
        "Which engineers are documented in these records?",
        "What incidents are recorded?",
        "Show all maintenance procedures"
    ]

    try:
        # Find top 6 most connected nodes (by degree) in the tenant graph
        top_nodes = neo4j_client.run_query(
            """
            MATCH (n)
            WHERE n.tenant_id = $tenant_id AND n.name IS NOT NULL
            WITH n, labels(n)[0] AS label, size([(n)--()]) AS degree
            ORDER BY degree DESC
            LIMIT 6
            RETURN n.name AS name, label
            """,
            {"tenant_id": tenant_id}
        )

        if not top_nodes:
            return {"suggestions": FALLBACK_SUGGESTIONS}

        suggestions = []
        for node in top_nodes:
            name = node.get("name", "")
            label = node.get("label", "")
            if not name:
                continue
            if label in ("Asset", "Equipment"):
                suggestions.append(f"Explain {name} and its maintenance history")
                suggestions.append(f"What failures have been reported for {name}?")
                suggestions.append(f"Show the SOP and procedures linked to {name}")
            elif label == "Person":
                suggestions.append(f"What assets does {name} maintain?")
                suggestions.append(f"Show the expertise profile of {name}")
            elif label == "Incident":
                suggestions.append(f"What caused {name}?")
                suggestions.append(f"Show incidents similar to {name}")
            elif label == "Procedure":
                suggestions.append(f"Summarize the procedure: {name}")
                suggestions.append(f"Which assets follow the procedure {name}?")
            elif label == "Regulation":
                suggestions.append(f"Which assets comply with {name}?")
                suggestions.append(f"What gaps exist against {name}?")

        # Deduplicate and return top 6
        seen = set()
        unique = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return {"suggestions": unique[:6] if unique else FALLBACK_SUGGESTIONS}

    except Exception as e:
        return {"suggestions": FALLBACK_SUGGESTIONS}

@router.get("/api/assets/{asset_name}/timeline")
def get_asset_timeline(asset_name: str, tenant_id: str = Depends(get_current_tenant_id)):
    if asset_name == "Pump P-101":
        return {
            "asset_name": asset_name,
            "events": [
                {"date": "2019-03-01", "type": "installation", "title": "Installed", "source_doc": "Maintenance Log #001"},
                {"date": "2021-02-15", "type": "incident", "title": "Seal Failure", "source_doc": "Incident Report #033"},
                {"date": "2023-08-14", "type": "incident", "title": "Seal Rupture", "source_doc": "Incident Report #033"},
                {"date": "2024-01-10", "type": "inspection", "title": "Annual Inspection", "source_doc": "Inspection Report #052"},
                {"date": "2026-08-12", "type": "upcoming", "title": "Next inspection due", "source_doc": None, "overdue": False}
            ]
        }
    return {"asset_name": asset_name, "events": []}

class ExplainRequest(BaseModel):
    prior_answer: str
    query: str
    context_ids: List[int]

@router.post("/api/copilot/explain")
async def explain_reasoning(payload: ExplainRequest, tenant_id: str = Depends(get_current_tenant_id)):
    async def sse():
        yield "data: " + json.dumps({"type": "stage", "stage": "reasoning", "status": "running"}) + "\n\n"
        await asyncio.sleep(0.5)
        reasoning = f"I based my answer to '{payload.query}' heavily on the connected incident reports for the asset, specifically focusing on the timeline of failures. I assumed normal operating conditions as stated in the manual."
        words = reasoning.split(" ")
        for word in words:
            yield "data: " + json.dumps({"type": "token", "content": word + " "}) + "\n\n"
            await asyncio.sleep(0.05)
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"
    return StreamingResponse(sse(), media_type="text/event-stream")
