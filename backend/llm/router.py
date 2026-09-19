import time
import logging
from typing import Generator, Optional, Dict, Any, List
from backend.config import get_settings
from backend.llm.factory import get_provider_instance
from backend.llm.registry import registry
from backend.llm.metrics import record_llm_latency, record_llm_usage, record_fallback

logger = logging.getLogger(__name__)

class LLMRouter:
    def __init__(self):
        self.settings = get_settings()

    def _get_providers(self, task: str) -> List[Dict[str, str]]:
        """
        Get the ordered list of providers from the registry for a specific task.
        Applies ENABLE_CLOUD_FALLBACK settings.
        """
        providers_config = registry.get_providers_for_task(task)
        if not providers_config:
            # Fallback to default if task not found
            providers_config = [
                {"provider": self.settings.LLM_PROVIDER, "model": getattr(self.settings, f"{self.settings.LLM_PROVIDER.upper()}_MODEL", "default")}
            ]
            
        filtered = []
        for config in providers_config:
            p = config["provider"]
            
            if p == "ollama" and not getattr(self.settings, "OLLAMA_ENABLED", True):
                continue
                
            # Enforce cloud fallback restriction
            is_cloud = p not in ["ollama", "local"]
            if is_cloud and not getattr(self.settings, "ENABLE_CLOUD_FALLBACK", False):
                continue
            
            filtered.append(config)
            
        return filtered

    def _execute_with_fallback(self, task: str, action: str, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Any:
        providers = self._get_providers(task)
        if not providers:
            raise RuntimeError(f"No available providers for task {task}")

        errors = []
        for i, provider_config in enumerate(providers):
            p_name = provider_config["provider"]
            m_name = provider_config["model"]
            
            if i > 0:
                logger.info(f"Triggering fallback to {p_name} ({m_name}) for task {task}")
                record_fallback()
                
            try:
                provider = get_provider_instance(p_name, m_name)
                
                # Check circuit breaker / health
                # Simple health check before execution
                if not provider.health_check():
                    logger.warning(f"Provider {p_name} failed health check. Skipping.")
                    errors.append(f"{p_name}: failed health check")
                    continue
                    
                start_time = time.time()
                
                if action == "generate":
                    result = provider.generate(prompt, system_prompt)
                    # We might want to count tokens manually since httpx doesn't always return usage natively unless we parse it.
                    # For simplicity, we just use a rough estimate if we don't have it.
                    record_llm_usage(p_name, m_name, len(prompt)//4, len(result)//4)
                elif action == "structured":
                    max_tokens = kwargs.get("max_tokens", 2000)
                    result = provider.structured(prompt, system_prompt, max_tokens)
                    record_llm_usage(p_name, m_name, len(prompt)//4, len(str(result))//4)
                elif action == "stream":
                    # For streaming, we yield directly. Tracking tokens is harder, done in the caller or wrapper.
                    result = provider.stream(prompt, system_prompt)
                    # Cannot accurately time streaming here without wrapping the generator.
                    return result
                else:
                    raise ValueError(f"Unknown action {action}")
                    
                duration_ms = (time.time() - start_time) * 1000.0
                record_llm_latency(p_name, m_name, duration_ms)
                
                return result
                
            except Exception as e:
                logger.error(f"Provider {p_name} failed during {action}: {e}")
                errors.append(f"{p_name}: {str(e)}")
                # If we have exhausted MAX_RETRIES, we could break, but here we just try next provider
                continue
                
        raise RuntimeError(f"All providers failed for task {task}. Errors: {errors}")

    def generate(self, task: str, prompt: str, system_prompt: Optional[str] = None) -> str:
        return self._execute_with_fallback(task, "generate", prompt, system_prompt)

    def structured(self, task: str, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        return self._execute_with_fallback(task, "structured", prompt, system_prompt, max_tokens=max_tokens)

    def stream(self, task: str, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        # Return the generator from the first successful provider
        # Note: Fallbacks during streaming are tricky. We only fallback if the initial connection fails.
        return self._execute_with_fallback(task, "stream", prompt, system_prompt)

llm_router = LLMRouter()
