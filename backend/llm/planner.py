import logging
from typing import Generator, Optional, Dict, Any
from backend.config import get_settings
from backend.llm.cache import semantic_cache
from backend.llm.router import llm_router

logger = logging.getLogger(__name__)

class AIExecutionPlanner:
    """
    Decides whether an LLM is actually needed, handles semantic caching, 
    and orchestrates the router.
    """
    def __init__(self):
        self.settings = get_settings()

    def generate(self, task: str, prompt: str, system_prompt: Optional[str] = None, use_cache: bool = True) -> str:
        # 1. Check Cache
        if use_cache:
            cached = semantic_cache.get(task, "any", prompt, system_prompt, "text")
            if cached:
                logger.info(f"AI Execution Planner: Cache hit for task '{task}'. Skipping LLM.")
                return cached

        # 2. Router Fallbacks
        logger.info(f"AI Execution Planner: Routing generation task '{task}'...")
        result = llm_router.generate(task, prompt, system_prompt)

        # 3. Store Cache
        if use_cache:
            semantic_cache.set(task, "any", prompt, result, system_prompt, "text")
            
        return result

    def structured(self, task: str, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000, use_cache: bool = True) -> Dict[str, Any]:
        # 1. Check Cache
        if use_cache:
            cached = semantic_cache.get(task, "any", prompt, system_prompt, "json")
            if cached:
                logger.info(f"AI Execution Planner: Cache hit for task '{task}'. Skipping LLM.")
                return cached

        # 2. Router Fallbacks
        logger.info(f"AI Execution Planner: Routing structured task '{task}'...")
        result = llm_router.structured(task, prompt, system_prompt, max_tokens)

        # 3. Store Cache
        if use_cache and "error" not in result:
            semantic_cache.set(task, "any", prompt, result, system_prompt, "json")
            
        return result

    def stream(self, task: str, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        # Streaming generally isn't cached in our simple implementation
        logger.info(f"AI Execution Planner: Routing stream task '{task}'...")
        yield from llm_router.stream(task, prompt, system_prompt)

planner = AIExecutionPlanner()
