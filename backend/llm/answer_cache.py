import redis
import json
import hashlib
import logging
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

def generate_cache_key(tenant_id: str, query: str) -> str:
    hash_obj = hashlib.md5(query.lower().strip().encode())
    return f"cache:{tenant_id}:{hash_obj.hexdigest()}"

def get_cached_answer(tenant_id: str, query: str) -> dict:
    try:
        key = generate_cache_key(tenant_id, query)
        cached = redis_client.get(key)
        if cached:
            logger.info(f"Cache hit for query: {query}")
            return json.loads(cached)
        return None
    except Exception as e:
        logger.warning(f"Redis cache read error: {e}")
        return None

def set_cached_answer(tenant_id: str, query: str, answer_data: dict, expire_seconds: int = 3600):
    try:
        key = generate_cache_key(tenant_id, query)
        redis_client.setex(key, expire_seconds, json.dumps(answer_data))
    except Exception as e:
        logger.warning(f"Redis cache write error: {e}")

def invalidate_tenant(tenant_id: str):
    try:
        pattern = f"cache:{tenant_id}:*"
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache entries for tenant {tenant_id}")
    except Exception as e:
        logger.warning(f"Redis cache invalidation error: {e}")
