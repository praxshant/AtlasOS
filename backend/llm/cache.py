import hashlib
import json
import logging
from typing import Optional, Any
import redis
from backend.config import get_settings
from backend.llm.metrics import record_cache_hit

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL)
except Exception as e:
    logger.error(f"Failed to connect cache to Redis: {e}")
    redis_client = None

class SemanticCache:
    """
    Semantic Cache for LLM responses.
    Uses SHA256 hashing of request parameters to quickly return cached results.
    """
    def __init__(self, ttl_seconds: int = 86400 * 7):
        self.ttl_seconds = ttl_seconds

    def _hash_request(self, provider: str, model: str, prompt: str, system_prompt: Optional[str] = None, format: str = "text") -> str:
        payload = f"{provider}:{model}:{prompt}:{system_prompt or ''}:{format}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, provider: str, model: str, prompt: str, system_prompt: Optional[str] = None, format: str = "text") -> Optional[Any]:
        if not settings.ENABLE_SEMANTIC_CACHE or redis_client is None:
            return None
        
        key = f"llm_cache:{self._hash_request(provider, model, prompt, system_prompt, format)}"
        try:
            cached = redis_client.get(key)
            if cached:
                logger.debug(f"Cache hit for key {key}")
                record_cache_hit()
                if format == "json":
                    return json.loads(cached.decode("utf-8"))
                return cached.decode("utf-8")
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
        return None

    def set(self, provider: str, model: str, prompt: str, response: Any, system_prompt: Optional[str] = None, format: str = "text"):
        if not settings.ENABLE_SEMANTIC_CACHE or redis_client is None:
            return
            
        key = f"llm_cache:{self._hash_request(provider, model, prompt, system_prompt, format)}"
        try:
            if format == "json":
                value = json.dumps(response)
            else:
                value = str(response)
            redis_client.setex(key, self.ttl_seconds, value)
            logger.debug(f"Cached response for key {key}")
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")

semantic_cache = SemanticCache()
