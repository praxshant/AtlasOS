from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel

from backend.graph.graph_analytics import graph_analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/centrality", response_model=List[Dict[str, Any]])
async def get_centrality(tenant_id: str = "default"):
    """Returns PageRank centrality scores for Equipment nodes."""
    try:
        results = graph_analytics.run_pagerank(tenant_id)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/communities", response_model=List[Dict[str, Any]])
async def get_communities(tenant_id: str = "default"):
    """Returns Louvain communities of Equipment."""
    try:
        results = graph_analytics.detect_communities(tenant_id)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/similar/{equipment_id}", response_model=List[Dict[str, Any]])
async def get_similar(equipment_id: str, tenant_id: str = "default"):
    """Returns similar equipment using Node Similarity."""
    try:
        results = graph_analytics.get_similar_equipment(equipment_id, tenant_id)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
