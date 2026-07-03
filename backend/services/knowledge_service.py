import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.db.postgres import Document, ProcessingJob
from backend.graph.neo4j_client import neo4j_client
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def get_system_metrics(db: Session, tenant_id: str = "default") -> Dict[str, Any]:
    """
    Returns unified system metrics computed from PostgreSQL and Neo4j.
    Used consistently across Dashboard, Risk, and Coverage pages.
    """
    from backend.vector.qdrant_client import qdrant_client
    from backend.config import get_settings
    settings = get_settings()

    # Get Qdrant vector count
    try:
        client = qdrant_client.get_client()
        if client:
            qdrant_res = client.count(collection_name=settings.QDRANT_COLLECTION_NAME)
            vector_count = qdrant_res.count
        else:
            vector_count = 0
    except Exception as e:
        logger.warning(f"Failed to fetch vector count: {e}")
        vector_count = 0

    # Get Neo4j node count
    try:
        node_res = neo4j_client.run_query("MATCH (n) WHERE n.tenant_id = $tenant_id RETURN count(n) as count", {"tenant_id": tenant_id})
        node_count = node_res[0]["count"] if node_res else 0
    except Exception:
        node_count = 0
    # 1. Assets (Asset or Equipment)
    try:
        asset_res = neo4j_client.run_query(
            "MATCH (n) WHERE (n:Asset OR n:Equipment) AND n.tenant_id = $tenant_id RETURN count(n) as count", 
            {"tenant_id": tenant_id}
        )
        industrial_assets = asset_res[0]["count"] if asset_res else 0
    except Exception:
        industrial_assets = 0
    
    # 2. Critical Gaps
    try:
        gaps_res = neo4j_client.run_query(
            "MATCH (n:MissingCategory) WHERE n.tenant_id = $tenant_id RETURN count(n) as count", 
            {"tenant_id": tenant_id}
        )
        critical_gaps = gaps_res[0]["count"] if gaps_res else 0
    except Exception:
        critical_gaps = 0

    # 3. Postgres Document & Job Stats
    doc_count = db.query(Document).filter(
        Document.tenant_id == tenant_id, 
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"])
    ).count()
    
    recent_uploads = db.query(Document).filter(
        Document.tenant_id == tenant_id, 
        Document.status.notin_(["deleted", "deleting", "failed", "failed_delete"]), 
        Document.upload_time >= datetime.utcnow() - timedelta(days=7)
    ).count()

    failed_uploads = db.query(Document).filter(
        Document.tenant_id == tenant_id, 
        Document.status.in_(["failed", "failed_delete"])
    ).count()
    
    processing_queue = db.query(ProcessingJob).filter(
        ProcessingJob.tenant_id == tenant_id, 
        ProcessingJob.status == "pending"
    ).count()

    # 4. Coverage % (Assets linked to >= 1 Procedure)
    if industrial_assets > 0:
        try:
            covered_res = neo4j_client.run_query(
                """
                MATCH (a)
                WHERE (a:Asset OR a:Equipment) AND a.tenant_id = $tenant_id
                MATCH (a)-[:FOLLOWS|HAS_PROCEDURE|DOCUMENTED_BY|DOCUMENTED_IN]-(p)
                WHERE p:Procedure OR p:LessonLearned OR p:SOP
                RETURN count(distinct a) as cnt
                """,
                {"tenant_id": tenant_id}
            )
            covered_count = covered_res[0]["cnt"] if covered_res else 0
            knowledge_coverage_pct = round((covered_count / industrial_assets) * 100, 1)
        except Exception:
            knowledge_coverage_pct = 0
    else:
        knowledge_coverage_pct = 0

    # 5. Risk % 
    risk_breakdown = get_risk_breakdown(tenant_id)
    high_critical_count = risk_breakdown["critical"] + risk_breakdown["high"]
    knowledge_risk_pct = round((high_critical_count / max(industrial_assets, 1)) * 100, 1) if industrial_assets > 0 else 0

    return {
        "industrial_assets": industrial_assets,
        "assets_delta_week": 0,  # Could be dynamic later
        "knowledge_coverage_pct": knowledge_coverage_pct,
        "coverage_delta": 0,
        "critical_gaps": critical_gaps,
        "engineers_at_risk": 0,
        "knowledge_risk_pct": knowledge_risk_pct,
        "processing_queue": processing_queue,
        "recent_uploads_7d": recent_uploads,
        "failed_uploads": failed_uploads,
        "total_documents": doc_count,
        "vector_count": vector_count,
        "node_count": node_count
    }

def get_risk_breakdown(tenant_id: str = "default") -> Dict[str, Any]:
    """
    Computes a risk breakdown (critical, high, medium, low) across all equipment.
    Formula: Risk Score = Incidents + (1 - Coverage)*10 + Missing SOPs*5 + Work Orders*2
    """
    query = """
    MATCH (a) WHERE (a:Asset OR a:Equipment) AND a.tenant_id = $tenant_id
    
    OPTIONAL MATCH (a)-[:AFFECTED_BY|INVOLVED_IN|CAUSED_BY|RELATED_TO]-(i:Incident)
    WITH a, count(distinct i) as incident_count
    
    OPTIONAL MATCH (a)-[:PERFORMED_ON]-(wo:WorkOrder)
    WITH a, incident_count, count(distinct wo) as wo_count
    
    OPTIONAL MATCH (a)-[:FOLLOWS|HAS_PROCEDURE|DOCUMENTED_BY|DOCUMENTED_IN]-(p)
    WHERE p:Procedure OR p:SOP
    WITH a, incident_count, wo_count, count(distinct p) as proc_count
    
    OPTIONAL MATCH (a)-[:HAS_KNOWLEDGE_GAP]-(gap)
    WITH a, incident_count, wo_count, proc_count, count(distinct gap) as gap_count
    
    RETURN a.name as name, incident_count, wo_count, proc_count, gap_count
    """
    breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    try:
        results = neo4j_client.run_query(query, {"tenant_id": tenant_id})
        if not results:
            return breakdown
    except Exception as e:
        logger.warning(f"Failed to fetch risk breakdown: {e}")
        return breakdown
    
    for row in results:
        incidents = row["incident_count"]
        wos = row["wo_count"]
        procs = row["proc_count"]
        gaps = row["gap_count"]
        
        # Risk heuristic
        score = (incidents * 15) + (wos * 5) + (gaps * 10)
        if procs == 0:
            score += 20
            
        if score >= 50:
            breakdown["critical"] += 1
        elif score >= 25:
            breakdown["high"] += 1
        elif score >= 10:
            breakdown["medium"] += 1
        else:
            breakdown["low"] += 1
            
    return breakdown
