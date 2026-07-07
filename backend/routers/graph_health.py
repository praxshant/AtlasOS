from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any

from backend.graph.graph_health import graph_health_monitor
from backend.utils.auth import get_current_tenant_id, get_current_user, User, check_role

router = APIRouter(prefix="/api/system/graph-health", tags=["system", "graph"])

@router.get("", response_model=Dict[str, Any])
async def get_graph_health(
    current_user: User = Depends(check_role(["admin", "engineer"])),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Returns a health report of the Knowledge Graph."""
    try:
        report = graph_health_monitor.generate_health_report(tenant_id)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
