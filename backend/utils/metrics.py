import time
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

def record_latency(metric_name: str, duration_ms: float):
    """
    Records the latency of an operation in milliseconds.
    Stores counts and sum in Redis for distributed aggregation.
    """
    if redis_client is None:
        return
    try:
        pipe = redis_client.pipeline()
        pipe.hincrbyfloat(f"metrics:latency:{metric_name}", "sum", duration_ms)
        pipe.hincrby(f"metrics:latency:{metric_name}", "count", 1)
        pipe.execute()
    except Exception as e:
        logger.error(f"Failed to record latency metric {metric_name}: {e}")

def record_token_usage(prompt_tokens: int, completion_tokens: int):
    """
    Records LLM token usage.
    """
    if redis_client is None:
        return
    try:
        pipe = redis_client.pipeline()
        pipe.incrby("metrics:tokens:prompt", prompt_tokens)
        pipe.incrby("metrics:tokens:completion", completion_tokens)
        pipe.incrby("metrics:tokens:total", prompt_tokens + completion_tokens)
        pipe.execute()
    except Exception as e:
        logger.error(f"Failed to record token usage: {e}")

def get_prometheus_metrics() -> str:
    """
    Generates Prometheus-compatible text output of the current system metrics.
    """
    lines = []
    
    # 1. Latency metrics
    services = ["openrouter", "neo4j", "qdrant", "postgres", "ingestion"]
    for s in services:
        total_sum = 0.0
        count = 0
        if redis_client:
            try:
                data = redis_client.hgetall(f"metrics:latency:{s}")
                total_sum = float(data.get(b"sum", 0.0)) / 1000.0  # Convert to seconds
                count = int(data.get(b"count", 0))
            except Exception:
                pass
                
        lines.append(f"# HELP atlasos_{s}_latency_seconds_total Sum of latency in seconds for {s}")
        lines.append(f"# TYPE atlasos_{s}_latency_seconds_total counter")
        lines.append(f"atlasos_{s}_latency_seconds_total {total_sum:.4f}")
        
        lines.append(f"# HELP atlasos_{s}_requests_total Total operations executed for {s}")
        lines.append(f"# TYPE atlasos_{s}_requests_total counter")
        lines.append(f"atlasos_{s}_requests_total {count}")
        
    # 2. Token metrics
    token_keys = ["prompt", "completion", "total"]
    for k in token_keys:
        count = 0
        if redis_client:
            try:
                val = redis_client.get(f"metrics:tokens:{k}")
                count = int(val) if val else 0
            except Exception:
                pass
        lines.append(f"# HELP atlasos_llm_tokens_{k}_total Cumulative count of {k} tokens")
        lines.append(f"# TYPE atlasos_llm_tokens_{k}_total counter")
        lines.append(f"atlasos_llm_tokens_{k}_total {count}")
        
    return "\n".join(lines) + "\n"
