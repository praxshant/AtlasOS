from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from backend.utils.auth import get_current_tenant_id
from backend.graph.neo4j_client import neo4j_client

router = APIRouter()

@router.get("")
def get_engineers(tenant_id: str = Depends(get_current_tenant_id)):
    """
    Returns the roster of engineers (Person nodes) with real graph metrics and summarized statistics.
    """
    engineers = neo4j_client.get_all_engineers(tenant_id=tenant_id)
    total_engineers = len(engineers)
    high_risk_count = sum(1 for e in engineers if e.get("succession_risk") in ("High", "Critical"))
    avg_expertise_score = round(sum(e.get("expertise_score", 0.0) for e in engineers) / max(1, total_engineers), 1)

    # Compute critical unprotected assets (assets with incident history but no safe experts)
    critical_assets_unprotected = 0
    try:
        query = """
        MATCH (a)
        WHERE (a:Asset OR a:Equipment) AND a.tenant_id = $tenant_id
        OPTIONAL MATCH (a)<-[:OCCURRED_ON]-(i:Incident)
        WITH a, count(distinct i) as incident_count
        WHERE incident_count > 0
        
        OPTIONAL MATCH (a)<-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY|KNOWLEDGE_OWNER_FOR]-(p)
        WHERE p.type = 'Person' OR p.entity_type = 'Person' OR 'Person' IN labels(p)
        RETURN a.name as asset, collect(p.name) as experts
        """
        critical_assets = neo4j_client.run_query(query, {"tenant_id": tenant_id})
        eng_risk_map = {e["name"]: e["succession_risk"] for e in engineers}
        
        for row in critical_assets:
            experts = [exp for exp in row.get("experts", []) if exp]
            if not experts:
                critical_assets_unprotected += 1
            else:
                if all(eng_risk_map.get(exp, "Low") in ("High", "Critical") for exp in experts):
                    critical_assets_unprotected += 1
    except Exception:
        pass

    summary = {
        "total_engineers": total_engineers,
        "high_risk_count": high_risk_count,
        "avg_expertise_score": avg_expertise_score,
        "critical_assets_unprotected": critical_assets_unprotected
    }

    return {
        "engineers": engineers,
        "summary": summary
    }

@router.get("/{name}/expertise")
def get_engineer_expertise(name: str, tenant_id: str = Depends(get_current_tenant_id)):
    """
    Returns detailed expertise profile for a specific engineer.
    """
    query = """
    MATCH (p {name: $name, tenant_id: $tenant_id})
    WHERE p.type = 'Person' OR p.entity_type = 'Person' OR 'Person' IN labels(p)
    
    OPTIONAL MATCH (p)-[:AUTHORED_BY|DOCUMENTED_BY_PERSON|WRITTEN_BY|SUBMITTED_BY|REPORTED_BY]-(d)
    WITH p, count(distinct d) as doc_count
    
    OPTIONAL MATCH (p)-[:INVOLVED_IN|REPORTED_BY]-(i:Incident)
    WITH p, doc_count, count(distinct i) as incident_count
    
    OPTIONAL MATCH (p)-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY]-(e)
    WHERE e:Equipment OR e:Asset
    WITH p, doc_count, incident_count, collect(distinct e.name) as equipment_owned
    
    RETURN p.name as name, p.role as role, doc_count, incident_count, equipment_owned, p.retirement_risk as retirement_risk
    """
    results = neo4j_client.run_query(query, {"name": name, "tenant_id": tenant_id})
    
    if not results:
        raise HTTPException(status_code=404, detail="Engineer not found")
        
    row = results[0]
    doc_count = row["doc_count"]
    inc_count = row["incident_count"]
    equipment = row["equipment_owned"]
    
    score = min(1.0, (doc_count * 0.1) + (inc_count * 0.05) + (len(equipment) * 0.15))
    
    risk_score = 0.2
    if row["retirement_risk"] == "HIGH":
        risk_score = 0.9
    elif len(equipment) > 3 and doc_count < 2:
        risk_score = 0.8
    elif len(equipment) > 1:
        risk_score = 0.5
        
    expertise_areas = []
    if equipment:
        expertise_areas.append("Equipment Ops")
    if doc_count > 0:
        expertise_areas.append("Documentation")
    if not expertise_areas:
        expertise_areas.append("General Maintenance")
        
    return {
        "name": row["name"],
        "role": row.get("role") or "Engineer",
        "contribution_score": round(score, 2),
        "risk_score": risk_score,
        "expertise_areas": expertise_areas,
        "equipment_owned": equipment,
        "documents_count": doc_count,
        "incidents_count": inc_count
    }

@router.get("/risk/{equipment}")
def get_equipment_expert_risk(equipment: str, tenant_id: str = Depends(get_current_tenant_id)):
    """
    Finds all engineers associated with a piece of equipment and checks their risk levels.
    """
    query = """
    MATCH (e) WHERE (e:Equipment OR e:Asset) AND e.name = $equipment AND e.tenant_id = $tenant_id
    OPTIONAL MATCH (e)-[:MAINTAINED_BY|INSPECTED_BY|OPERATED_BY|KNOWLEDGE_OWNER|OWNED_BY]-(p)
    WHERE p.type = 'Person' OR p.entity_type = 'Person' OR 'Person' IN labels(p)
    RETURN p.name as name, p.retirement_risk as retirement_risk
    """
    results = neo4j_client.run_query(query, {"equipment": equipment, "tenant_id": tenant_id})
    
    if not results or (len(results) == 1 and results[0]["name"] is None):
        return {"risks": []}
        
    risks = []
    for row in results:
        name = row["name"]
        if not name:
            continue
            
        r_risk = row["retirement_risk"]
        risk_score = 0.9 if r_risk == "HIGH" else 0.3
        
        risks.append({
            "name": name,
            "engineer": name,
            "knowledge_score": 0.85, # hardcoded heuristic
            "risk_score": risk_score,
            "has_backup": len([r for r in results if r["name"]]) > 1
        })
        
    return {"risks": risks}
