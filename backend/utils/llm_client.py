import json
import logging
from typing import Generator, Optional, Dict, Any
from backend.utils.llm_provider import get_provider

logger = logging.getLogger(__name__)

def complete(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Standard text completion returning a string.
    """
    try:
        provider = get_provider()
        return provider.complete(prompt, system_prompt)
    except Exception as e:
        logger.error(f"Completion failed: {e}")
        from backend.config import get_settings
        settings = get_settings()
        if settings.OLLAMA_ENABLED:
            logger.info("Falling back to Ollama due to completion error.")
            from backend.utils.llm_provider import OllamaProvider
            return OllamaProvider().complete(prompt, system_prompt)
        raise e

def structured_complete(prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
    """
    Structured text completion returning a parsed JSON dictionary.
    """
    try:
        provider = get_provider()
        return provider.structured_complete(prompt, system_prompt, max_tokens)
    except Exception as e:
        logger.error(f"Structured completion failed: {e}")
        from backend.config import get_settings
        settings = get_settings()
        if settings.OLLAMA_ENABLED:
            logger.info("Falling back to Ollama due to structured completion error.")
            from backend.utils.llm_provider import OllamaProvider
            return OllamaProvider().structured_complete(prompt, system_prompt, max_tokens)
        return {"error": "request_failed", "raw": str(e)}

def stream_complete(prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
    """
    Streaming text completion returning a token generator.
    """
    try:
        provider = get_provider()
        yield from provider.stream_complete(prompt, system_prompt)
    except Exception as e:
        logger.error(f"Streaming completion failed: {e}")
        from backend.config import get_settings
        settings = get_settings()
        if settings.OLLAMA_ENABLED:
            logger.info("Falling back to Ollama due to streaming completion error.")
            from backend.utils.llm_provider import OllamaProvider
            yield from OllamaProvider().stream_complete(prompt, system_prompt)
        else:
            yield f"\\n[Error during generation: {e}]"

def complete_with_context_limit(prompt: str, system_prompt: Optional[str] = None, max_context_tokens: int = 6000) -> str:
    """
    Truncate prompt to stay within context limit.
    Simple character-based approximation: 1 token ≈ 4 characters.
    max_chars = max_context_tokens * 4
    """
    max_chars = max_context_tokens * 4
    system_chars = len(system_prompt) if system_prompt else 0
    prompt_chars = len(prompt)
    
    if system_chars + prompt_chars <= max_chars:
        return prompt
        
    allowed_prompt_chars = max_chars - system_chars
    if allowed_prompt_chars <= 0:
        return prompt
        
    # Truncate earlier context from the front
    truncated_prompt = "..." + prompt[-(allowed_prompt_chars - 3):]
    return truncated_prompt

# --- Legacies for Backwards Compatibility ---

def call_llm(prompt: str, system_prompt: Optional[str] = None, response_format: Optional[str] = None) -> str:
    """
    Legacy wrapper. Routes to complete() or structured_complete() based on response_format.
    """
    if response_format == "json":
        res_dict = structured_complete(prompt, system_prompt)
        return json.dumps(res_dict)
    return complete(prompt, system_prompt)

def call_llm_streaming(prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
    """
    Legacy wrapper. Routes to stream_complete().
    """
    return stream_complete(prompt, system_prompt)
