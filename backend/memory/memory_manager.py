import time
from typing import Dict, List, Any

class MemoryManager:
    """
    Manages Short-term (conversational) and Long-term (tenant-scoped) memory for AtlasOS.
    """
    def __init__(self):
        # Short-term memory: session_id -> List of conversation turns
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}
        # Long-term memory: tenant_id -> Cache of entities, analytics, reasoning paths
        self.tenant_cache: Dict[str, Dict[str, Any]] = {}

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        return self.sessions.get(session_id, [])

    def add_interaction(self, session_id: str, query: str, answer: str, reasoning_path: List[str] = None):
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        self.sessions[session_id].append({
            "timestamp": time.time(),
            "query": query,
            "answer": answer,
            "reasoning_path": reasoning_path or []
        })

    def get_tenant_cache(self, tenant_id: str, key: str) -> Any:
        return self.tenant_cache.get(tenant_id, {}).get(key)

    def set_tenant_cache(self, tenant_id: str, key: str, value: Any):
        if tenant_id not in self.tenant_cache:
            self.tenant_cache[tenant_id] = {}
        self.tenant_cache[tenant_id][key] = value

    def invalidate_tenant(self, tenant_id: str):
        """Called when the underlying graph data changes (e.g., re-ingestion)."""
        if tenant_id in self.tenant_cache:
            self.tenant_cache[tenant_id] = {}

memory_manager = MemoryManager()
