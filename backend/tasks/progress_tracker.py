import json
import redis
import logging
from typing import Dict, Any
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class ProgressTracker:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL)
        
    def _key(self, job_id: str) -> str:
        return f"atlasos:job_progress:{job_id}"
        
    def init_job(self, job_id: str, total_chunks: int = 0):
        data = {
            "status": "processing",
            "stage": "started",
            "progress": 0,
            "chunks_processed": 0,
            "total_chunks": total_chunks,
            "error": None
        }
        self.redis.setex(self._key(job_id), 86400, json.dumps(data)) # 24h expiry
        
    def update_stage(self, job_id: str, stage: str, progress: int = None):
        key = self._key(job_id)
        raw = self.redis.get(key)
        if raw:
            data = json.loads(raw)
            data["stage"] = stage
            if progress is not None:
                data["progress"] = progress
            self.redis.setex(key, 86400, json.dumps(data))
            
    def increment_chunk(self, job_id: str):
        key = self._key(job_id)
        raw = self.redis.get(key)
        if raw:
            data = json.loads(raw)
            data["chunks_processed"] += 1
            if data["total_chunks"] > 0:
                data["progress"] = min(99, int((data["chunks_processed"] / data["total_chunks"]) * 100))
            self.redis.setex(key, 86400, json.dumps(data))
            
    def complete_job(self, job_id: str):
        key = self._key(job_id)
        raw = self.redis.get(key)
        if raw:
            data = json.loads(raw)
            data["status"] = "completed"
            data["stage"] = "done"
            data["progress"] = 100
            self.redis.setex(key, 86400, json.dumps(data))
            
    def fail_job(self, job_id: str, error: str):
        key = self._key(job_id)
        raw = self.redis.get(key)
        data = json.loads(raw) if raw else {}
        data["status"] = "failed"
        data["error"] = error
        self.redis.setex(key, 86400, json.dumps(data))
        
    def get_progress(self, job_id: str) -> Dict[str, Any]:
        raw = self.redis.get(self._key(job_id))
        if raw:
            return json.loads(raw)
        return {"status": "unknown"}

progress_tracker = ProgressTracker()
