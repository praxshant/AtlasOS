import logging
import redis
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL)
except Exception as e:
    logger.error(f"Failed to connect metrics to Redis: {e}")
    redis_client = None

def record_llm_latency(provider: str, model: str, duration_ms: float):
    if redis_client is None: return
    try:
        pipe = redis_client.pipeline()
        pipe.hincrbyfloat(f"metrics:llm:latency:{provider}", "sum", duration_ms)
        pipe.hincrby(f"metrics:llm:latency:{provider}", "count", 1)
        pipe.hincrbyfloat(f"metrics:llm:latency:{provider}:{model}", "sum", duration_ms)
        pipe.hincrby(f"metrics:llm:latency:{provider}:{model}", "count", 1)
        pipe.execute()
    except Exception as e:
        logger.error(f"Failed to record LLM latency: {e}")

def record_llm_usage(provider: str, model: str, prompt_tokens: int, completion_tokens: int):
    if redis_client is None: return
    try:
        pipe = redis_client.pipeline()
        pipe.incrby(f"metrics:llm:tokens:{provider}:prompt", prompt_tokens)
        pipe.incrby(f"metrics:llm:tokens:{provider}:completion", completion_tokens)
        pipe.incrby(f"metrics:llm:tokens:{provider}:total", prompt_tokens + completion_tokens)
        pipe.execute()
    except Exception as e:
        logger.error(f"Failed to record LLM usage: {e}")

def record_cache_hit():
    if redis_client is None: return
    try:
        redis_client.incr("metrics:llm:cache_hits")
    except Exception as e:
        logger.error(f"Failed to record cache hit: {e}")

def record_fallback():
    if redis_client is None: return
    try:
        redis_client.incr("metrics:llm:fallbacks")
    except Exception as e:
        logger.error(f"Failed to record fallback: {e}")
