import json
import logging
import os
import tempfile
from typing import Generator, Optional, Dict, Any
import httpx
from filelock import FileLock
from backend.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Cross-process lock to prevent concurrent VRAM loads on single GPU
LOCK_FILE = os.path.join(tempfile.gettempdir(), "ollama_gpu.lock")
ollama_lock = FileLock(LOCK_FILE)

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": self.model, "messages": messages, "stream": False}
        with ollama_lock:
            res = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=120.0)
            res.raise_for_status()
            return res.json().get("message", {}).get("content", "")

    def structured(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model, 
            "messages": messages, 
            "stream": False, 
            "format": "json",
            "options": {"temperature": 0.1}
        }
        with ollama_lock:
            res = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=300.0)
            res.raise_for_status()
            content = res.json().get("message", {}).get("content", "{}")
        try:
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to parse JSON from Ollama: {e}")
            return {"error": "parse_failed", "raw": content[:1000]}

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": self.model, "messages": messages, "stream": True}
        with ollama_lock:
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

    def health_check(self) -> bool:
        try:
            res = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return res.status_code == 200
        except:
            return False
