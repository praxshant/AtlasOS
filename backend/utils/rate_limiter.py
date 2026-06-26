import time
import logging
import redis
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL)
except Exception as e:
    logger.error(f"Failed to connect rate limiter to Redis: {e}")
    redis_client = None

def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """
    Checks if a key (e.g., user_id or IP + endpoint) exceeds the rate limit.
    Uses a Redis sliding window sorted set. Fail-open if Redis is unavailable.
    Returns: True if rate limited, False if request is allowed.
    """
    if redis_client is None:
        return False
        
    now = time.time()
    cutoff = now - window_seconds
    
    try:
        pipe = redis_client.pipeline()
        # 1. Remove elements older than the current window cutoff
        pipe.zremrangebyscore(key, 0, cutoff)
        # 2. Count members in the set (requests made within the current window)
        pipe.zcard(key)
        # 3. Add the current timestamp as a new request
        pipe.zadd(key, {f"{now}-{window_seconds}": now})
        # 4. Set expiry to clean up memory
        pipe.expire(key, window_seconds + 5)
        # Execute atomic transaction
        _, count, _, _ = pipe.execute()
        
        return count >= limit
    except Exception as e:
        logger.error(f"Redis rate limiting transaction error: {e}")
        # Fail open in production to keep services accessible if Redis goes down
        return False
