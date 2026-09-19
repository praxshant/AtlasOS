import json
import logging
from typing import Generator, Optional, Dict, Any
import httpx
from backend.llm.base import LLMProvider

logger = logging.getLogger(__name__)

class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _prepare_messages(self, prompt: str, system_prompt: Optional[str]) -> list:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        payload = {
            "model": self.model,
            "messages": self._prepare_messages(prompt, system_prompt),
            "max_tokens": 1500
        }
        res = httpx.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=60.0)
        res.raise_for_status()
        return res.json().get("choices", [{}])[0].get("message", {}).get("content", "")

    def structured(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": self._prepare_messages(prompt, system_prompt),
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }
        res = httpx.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=120.0)
        res.raise_for_status()
        content = res.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try:
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to parse structured JSON: {e}")
            return {"error": "parse_failed", "raw": content[:1000]}

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        payload = {
            "model": self.model,
            "messages": self._prepare_messages(prompt, system_prompt),
            "stream": True,
            "max_tokens": 1500
        }
        with httpx.stream("POST", f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=120.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        data = json.loads(line[6:])
                        content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except:
                        pass

    def health_check(self) -> bool:
        try:
            # Simplest health check is a tiny completion or models list
            res = httpx.get(f"{self.base_url}/models", headers=self.headers, timeout=5.0)
            return res.status_code == 200
        except:
            return False
