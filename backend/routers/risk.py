from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime, timedelta
import json
from pydantic import BaseModel

from backend.db.postgres import get_db
from backend.utils.auth import get_current_user, get_current_tenant_id
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client
from backend.config import get_settings

router = APIRouter()
settings = get_settings()

# ─────────────────────────────────────────────
# GET /api/risk/assets
# Returns assets sorted by risk score descending
# ─────────────────────────────────────────────
@router.get("/assets")
def get_risk_assets(
    db = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Returns risk profiles for each asset using a unified scoring heuristic with live metrics.
    """
    query = """
    MATCH (a) WHERE (a:Asset OR a:Equipment) AND a.tenant_id = $tenant_id
    
    OPTIONAL MATCH (a)-[:AFFECTED_BY|INVOLVED_IN|CAUSED_BY|RELATED_TO]-(i:Incident)
    WITH a, count(distinct i) as incident_count
    
    OPTIONAL MATCH (a)-[:PERFORMED_ON]-(wo:WorkOrder)
    WITH a, incident_count, count(distinct wo) as wo_count
    
    OPTIONAL MATCH (a)-[:FOLLOWS|HAS_PROCEDURE|DOCUMENTED_BY|DOCUMENTED_IN]-(p)
    WHERE p:Procedure OR p:SOP
    WITH a, incident_count, wo_count, count(distinct p) as proc_count, collect(distinct p) as sops
    
    OPTIONAL MATCH (a)-[:HAS_KNOWLEDGE_GAP]-(gap)
    WITH a, incident_count, wo_count, proc_count, sops, count(distinct gap) as gap_count
    
    OPTIONAL MATCH (a)<-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY|KNOWLEDGE_OWNER_FOR]-(p:Person)
    WHERE p.retirement_risk = 'HIGH' OR p.succession_risk IN ['High', 'Critical']
    WITH a, incident_count, wo_count, proc_count, sops, gap_count, collect(distinct p.name) as retiring_experts
    
    OPTIONAL MATCH (sop)-[:DOCUMENTED_IN]-(d:Document)
    WHERE sop IN sops
    WITH a, incident_count, wo_count, proc_count, gap_count, retiring_experts, collect(distinct coalesce(d.updated_at, d.created_at)) as dates
    
    RETURN a.name as name, labels(a)[0] as label, incident_count, wo_count, proc_count, gap_count, retiring_experts, dates
    """
    
    results_raw = neo4j_client.run_query(query, {"tenant_id": tenant_id})
    if not results_raw:
        return []

    results = []
    
    for row in results_raw:
        asset_name = row["name"]
        asset_type = row["label"]
        incidents = row["incident_count"]
        wos = row["wo_count"]
        procs = row["proc_count"]
        gaps = row["gap_count"]
        retiring_experts = row.get("retiring_experts") or []
        dates = row.get("dates") or []
        
        # Risk heuristic (sync with knowledge_service.py)
        score = (incidents * 15) + (wos * 5) + (gaps * 10)
        if procs == 0:
            score += 20
            
        score = min(100, score)
            
        if score >= 50:
            risk_level = "Critical"
        elif score >= 25:
            risk_level = "High"
        elif score >= 10:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        # Build top reason
        reasons = []
        if incidents >= 1:
            reasons.append(f"{incidents} recent incidents")
        if gaps > 0:
            reasons.append(f"{gaps} missing SOPs")
        if procs == 0:
            reasons.append(f"No active procedures")
        if wos > 0:
            reasons.append(f"{wos} active work orders")
            
        top_reason = " + ".join(reasons) if reasons else "Low documentation coverage"

        # Build recommendation
        actions = []
        if gaps > 0:
            actions.append("Create missing SOPs")
        if procs == 0:
            actions.append("Document standard operating procedures")
        if incidents > 0:
            actions.append("Review incident root causes")
            
        recommended_action = ". ".join(actions) if actions else "Review documentation coverage"

        # Calculate SOP age in days dynamically
        sop_age_days = 0
        if dates:
            parsed_dates = []
            for raw_date in dates:
                if not raw_date:
                    continue
                try:
                    if isinstance(raw_date, str):
                        dt_str = raw_date
                        if dt_str.endswith('Z'):
                            dt_str = dt_str[:-1]
                        if '+' in dt_str:
                            dt_str = dt_str.split('+')[0]
                        parsed_dates.append(datetime.fromisoformat(dt_str))
                    elif isinstance(raw_date, (int, float)):
                        parsed_dates.append(datetime.utcfromtimestamp(raw_date / 1000.0 if raw_date > 1e11 else raw_date))
                    elif isinstance(raw_date, datetime):
                        parsed_dates.append(raw_date)
                except Exception:
                    pass
            if parsed_dates:
                newest_date = max(parsed_dates)
                if newest_date.tzinfo is not None:
                    newest_date = newest_date.replace(tzinfo=None)
                sop_age_days = max(0, (datetime.utcnow() - newest_date).days)

        results.append({
            "asset_name": asset_name,
            "asset_type": asset_type,
            "risk_score": score,
            "risk_level": risk_level,
            "factors": {
                "incident_count_2yr": incidents,
                "gap_count": gaps,
                "retiring_experts": retiring_experts,
                "sop_age_days": sop_age_days
            },
            "top_risk_reason": top_reason,
            "recommended_action": recommended_action,
            "estimated_downtime_cost": 500000 if "Reactor" in asset_name else 250000,
        })

    # Sort by risk score descending
    results.sort(key=lambda x: x["risk_score"], reverse=True)
    return results[:20]


# ─────────────────────────────────────────────
# GET /api/risk/timeline
# Returns knowledge decay events sorted by date
# ─────────────────────────────────────────────
@router.get("/timeline")
def get_risk_timeline(
    db = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id)
):
    events = []
    today = datetime.utcnow()

    # Engineer retirement events from Neo4j
    try:
        eng_query = """
        MATCH (p:Person)
        WHERE p.tenant_id = $tenant_id AND p.retirement_risk IS NOT NULL
        RETURN p.name as name, p.retirement_risk as retirement_risk,
               p.estimated_retirement_date as retirement_date
        """
        neo4j_engineers = neo4j_client.run_query(eng_query, {"tenant_id": tenant_id})
        for eng in neo4j_engineers:
            events.append({
                "type": "engineer_retirement",
                "label": f"{eng['name']} retirement window",
                "detail": "Retirement date approaching",
                "date": eng.get("retirement_date", (today + timedelta(days=365)).isoformat()),
                "severity": "critical" if eng.get("retirement_risk") == "HIGH" else "warning",
                "entity": eng["name"]
            })
    except Exception:
        pass

    # SOP aging events from Neo4j
    try:
        sop_query = """
        MATCH (p:Procedure)
        WHERE p.tenant_id = $tenant_id
        OPTIONAL MATCH (p)-[:DOCUMENTED_IN]-(d:Document)
        RETURN p.name as name, coalesce(d.updated_at, d.created_at) as last_updated,
               p.asset_name as asset_name
        """
        sops = neo4j_client.run_query(sop_query, {"tenant_id": tenant_id})
        for sop in sops:
            if not sop.get("last_updated"):
                continue
            raw = sop["last_updated"]
            sop_date = datetime.fromisoformat(str(raw)) if isinstance(raw, str) else raw
            age_days = (today - sop_date).days
            if age_days > 365:
                severity = "critical" if age_days > 1825 else "warning"
                years = age_days // 365
                events.append({
                    "type": "sop_aging",
                    "label": f"{sop['name']} — {years}yr outdated",
                    "detail": f"Last updated {age_days} days ago. Review recommended.",
                    "date": sop_date.isoformat(),
                    "severity": severity,
                    "entity": sop.get("asset_name", sop["name"])
                })
    except Exception:
        pass

    # Sort events by date ascending
    events.sort(key=lambda x: x["date"])
    return {"events": events}
