import json
import logging
from typing import Generator, Optional, Dict, Any
import httpx
from backend.llm.base import LLMProvider

logger = logging.getLogger(__name__)

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500
        }
        if system_prompt:
            payload["system"] = system_prompt
            
        res = httpx.post(f"{self.base_url}/messages", headers=self.headers, json=payload, timeout=60.0)
        res.raise_for_status()
        content_blocks = res.json().get("content", [])
        if content_blocks:
            return content_blocks[0].get("text", "")
        return ""

    def structured(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        # Anthropic doesn't have a strict JSON mode in the same way, but we can force it via prompt
        if system_prompt:
            system_prompt += "\n\nIMPORTANT: Return ONLY a valid JSON object. No markdown wrappers, no explanations."
        else:
            system_prompt = "Return ONLY a valid JSON object. No markdown wrappers."
            
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "system": system_prompt
        }
        
        res = httpx.post(f"{self.base_url}/messages", headers=self.headers, json=payload, timeout=120.0)
        res.raise_for_status()
        content = ""
        content_blocks = res.json().get("content", [])
        if content_blocks:
            content = content_blocks[0].get("text", "")
            
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            import re
            json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_block:
                try: return json.loads(json_block.group(1))
                except: pass
            return {"error": "parse_failed", "raw": content[:1000]}

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500,
            "stream": True
        }
        if system_prompt:
            payload["system"] = system_prompt
            
        with httpx.stream("POST", f"{self.base_url}/messages", headers=self.headers, json=payload, timeout=120.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "content_block_delta":
                            yield data["delta"].get("text", "")
                    except:
                        pass

    def health_check(self) -> bool:
        # Simplest ping for Anthropic
        try:
            res = httpx.post(f"{self.base_url}/messages", headers=self.headers, json={"model": self.model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}, timeout=5.0)
            return res.status_code == 200
        except:
            return False
