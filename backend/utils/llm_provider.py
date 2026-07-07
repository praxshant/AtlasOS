import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Generator, Optional, Dict, Any
import httpx
from openai import OpenAI

from backend.config import get_settings
from backend.utils.metrics import record_latency, record_token_usage
from backend.utils.circuit_breaker import openrouter_breaker

logger = logging.getLogger(__name__)

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        pass
        
    @abstractmethod
    def structured_complete(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        pass

    @abstractmethod
    def stream_complete(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        pass


class OpenRouterProvider(LLMProvider):
    def __init__(self):
        self.settings = get_settings()
        if not self.settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY not set")
        self.client = OpenAI(
            api_key=self.settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        self.model = self.settings.OPENROUTER_MODEL
        
    def _track_quota(self):
        try:
            import redis
            from datetime import datetime
            r = redis.Redis.from_url(self.settings.CELERY_BROKER_URL)
            today = datetime.utcnow().strftime("%Y-%m-%d")
            key = f"quota:openrouter:{today}"
            r.incr(key)
            r.expire(key, 86400 * 2) # expire in 2 days
        except Exception as e:
            logger.warning(f"Failed to track quota: {e}")

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start_time = time.time()
        def _do():
            return self.client.chat.completions.create(model=self.model, messages=messages, max_tokens=1000)
            
        res = openrouter_breaker.call(_do)
        self._track_quota()
        duration_ms = (time.time() - start_time) * 1000.0
        record_latency("openrouter", duration_ms)
        if hasattr(res, "usage") and res.usage:
            record_token_usage(res.usage.prompt_tokens, res.usage.completion_tokens)
            
        return res.choices[0].message.content or ""

    def structured_complete(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start_time = time.time()
        def _do(msgs):
            return self.client.chat.completions.create(
                model=self.model, messages=msgs,
                response_format={"type": "json_object"}, max_tokens=max_tokens
            )
            
        res = openrouter_breaker.call(_do, messages)
        self._track_quota()
        duration_ms = (time.time() - start_time) * 1000.0
        record_latency("openrouter", duration_ms)
        if hasattr(res, "usage") and res.usage:
            record_token_usage(res.usage.prompt_tokens, res.usage.completion_tokens)
            
        content = res.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            import re
            json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_block:
                try: return json.loads(json_block.group(1))
                except: pass
            
            # Retry mechanism logic
            logger.warning("structured_complete parse failed, retrying...")
            retry_msgs = messages.copy()
            retry_msgs[-1]["content"] += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown."
            res2 = openrouter_breaker.call(_do, retry_msgs)
            self._track_quota()
            content2 = res2.choices[0].message.content or "{}"
            try:
                return json.loads(content2)
            except:
                return {"error": "parse_failed", "raw": content2[:1000]}

    def stream_complete(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start_time = time.time()
        def _do():
            return self.client.chat.completions.create(
                model=self.model, messages=messages, stream=True, max_tokens=1500
            )
            
        res = openrouter_breaker.call(_do)
        self._track_quota()
        
        token_count = 0
        for chunk in res:
            delta = chunk.choices[0].delta.content
            if delta:
                token_count += 1
                yield delta
                
        duration_ms = (time.time() - start_time) * 1000.0
        record_latency("openrouter", duration_ms)


class OllamaProvider(LLMProvider):
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.OLLAMA_BASE_URL.rstrip('/')
        self.model = self.settings.OLLAMA_MODEL
        
    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": self.model, "messages": messages, "stream": False}
        res = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=120.0)
        res.raise_for_status()
        return res.json().get("message", {}).get("content", "")

    def structured_complete(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": self.model, "messages": messages, "stream": False, "format": "json"}
        res = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=300.0)
        res.raise_for_status()
        content = res.json().get("message", {}).get("content", "{}")
        try:
            return json.loads(content)
        except:
            return {"error": "parse_failed", "raw": content[:1000]}

    def stream_complete(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": self.model, "messages": messages, "stream": True}
        with httpx.stream("POST", f"{self.base_url}/api/chat", json=payload, timeout=120.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except:
                        pass


def get_provider() -> LLMProvider:
    settings = get_settings()
    
    # Optional logic: if LLM_PROVIDER == "ollama", force Ollama
    if settings.LLM_PROVIDER.lower() == "ollama":
        if not settings.OLLAMA_ENABLED:
            logger.warning("LLM_PROVIDER is ollama, but OLLAMA_ENABLED=False. Using OpenRouter instead.")
        else:
            return OllamaProvider()
            
    # Default to OpenRouter with Fallback
    try:
        return OpenRouterProvider()
    except Exception as e:
        logger.warning(f"OpenRouter initialization failed: {e}")
        if settings.OLLAMA_ENABLED:
            logger.info("Falling back to OllamaProvider")
            return OllamaProvider()
        raise e
