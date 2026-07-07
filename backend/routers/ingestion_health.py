from fastapi import APIRouter, Depends
import redis
from datetime import datetime
from backend.config import get_settings
from backend.utils.auth import get_current_user

router = APIRouter()

@router.get("/api/ingestion/health")
def get_ingestion_health():
    settings = get_settings()
    provider = settings.LLM_PROVIDER
    quota_limit = 50 # Example hardcode for OpenRouter Free Tier
    quota_used = 0
    
    if provider.lower() == "openrouter":
        try:
            r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
            today = datetime.utcnow().strftime("%Y-%m-%d")
            key = f"quota:openrouter:{today}"
            val = r.get(key)
            if val:
                quota_used = int(val)
        except:
            pass

    return {
        "provider": provider,
        "quota_used": quota_used,
        "quota_limit": quota_limit if provider.lower() == "openrouter" else None,
        "ollama_fallback_enabled": settings.OLLAMA_ENABLED,
        "reset_at": "00:00 UTC",
        "status": "healthy" if quota_used < quota_limit else "exhausted"
    }
