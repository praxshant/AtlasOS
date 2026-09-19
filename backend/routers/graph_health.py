from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any

from backend.knowledge_engineering.graph_quality.auditor import run_health_audit
from backend.knowledge_engineering.graph_quality.healer import heal_graph
from backend.utils.auth import get_current_tenant_id, User, check_role

router = APIRouter(prefix="/api/system/graph-health", tags=["system", "graph"])

@router.get("", response_model=Dict[str, Any])
async def get_graph_health(
    current_user: User = Depends(check_role(["admin", "engineer"])),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Returns a health report of the Knowledge Graph (V2 Auditor)."""
    try:
        return run_health_audit(tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heal", response_model=Dict[str, Any])
async def heal_graph_endpoint(
    current_user: User = Depends(check_role(["admin"])),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    V2.5 Self-Healing: Patches orphan nodes and missing confidence scores,
    then returns a before/after audit diff.
    """
    try:
        pre_audit = run_health_audit(tenant_id)
        result = heal_graph(tenant_id)
        result["pre_heal_audit"] = pre_audit
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

