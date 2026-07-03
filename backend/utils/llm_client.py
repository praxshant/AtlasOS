import json
import logging
import time
from typing import Generator, Optional, Dict, Any
from openai import OpenAI
from backend.config import get_settings
from backend.utils.metrics import record_latency, record_token_usage

logger = logging.getLogger(__name__)
settings = get_settings()

# OpenRouter API Client lazy loader
_client = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY environment variable is not set")
        _client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
    return _client

def complete(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Standard text completion returning a string.
    """
    openai_client = get_client()
        
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    start_time = time.time()
    try:
        from backend.utils.circuit_breaker import openrouter_breaker
        logger.info("=== SYSTEM MESSAGE ===")
        logger.info(system_prompt if system_prompt else "[None]")
        logger.info("=== USER MESSAGE ===")
        logger.info(prompt)
        
        def _do_complete():
            return openai_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=messages,
                max_tokens=1000
            )
            
        response = openrouter_breaker.call(_do_complete)
        
        duration_ms = (time.time() - start_time) * 1000.0
        record_latency("openrouter", duration_ms)
        if hasattr(response, "usage") and response.usage:
            record_token_usage(response.usage.prompt_tokens, response.usage.completion_tokens)
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"OpenRouter completion failed: {e}")
        raise e

def structured_complete(prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
    """
    Structured text completion returning a parsed JSON dictionary.
    """
    openai_client = get_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    start_time = time.time()
    try:
        from backend.utils.circuit_breaker import openrouter_breaker
        logger.info("=== SYSTEM MESSAGE ===")
        logger.info(system_prompt if system_prompt else "[None]")
        logger.info("=== USER MESSAGE ===")
        logger.info(prompt)
        
        def _do_structured_complete(msgs):
            return openai_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=msgs,
                response_format={"type": "json_object"},
                max_tokens=max_tokens
            )
            
        response = openrouter_breaker.call(_do_structured_complete, messages)
        
        duration_ms = (time.time() - start_time) * 1000.0
        record_latency("openrouter", duration_ms)
        if hasattr(response, "usage") and response.usage:
            record_token_usage(response.usage.prompt_tokens, response.usage.completion_tokens)
        content = response.choices[0].message.content or "{}"
        
        def parse_content(response_text: str) -> Optional[Dict]:
            # LAYER 1: Direct JSON parse
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                pass
                
            # LAYER 2: Extract JSON block
            import re
            json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_block:
                try:
                    return json.loads(json_block.group(1))
                except json.JSONDecodeError:
                    pass
                    
            # LAYER 3: Find largest JSON-like object
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(response_text[start:end+1])
                except json.JSONDecodeError:
                    pass
            return None

        result = parse_content(content)
        
        if result is None or len(content) < 50:
            logger.warning(f"structured_complete parsing failed or empty. Retrying... Raw: {content[:500]}")
            retry_msgs = messages.copy()
            retry_msgs[-1]["content"] += "\n\nIMPORTANT: Respond ONLY with valid JSON. No explanation. No markdown. Just the JSON object."
            response2 = openrouter_breaker.call(_do_structured_complete, retry_msgs)
            content2 = response2.choices[0].message.content or "{}"
            result2 = parse_content(content2)
            if result2 is not None:
                return result2
            logger.warning(f"structured_complete retry failed. Raw: {content2[:500]}")
            return {"error": "parse_failed", "raw": content2[:1000]}
            
        return result
    except Exception as e:
        logger.error(f"OpenRouter structured completion failed: {e}")
        return {"error": "request_failed", "raw": str(e)}

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

def stream_complete(prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
    """
    Streaming text completion returning a token generator.
    """
    openai_client = get_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    start_time = time.time()
    try:
        from backend.utils.circuit_breaker import openrouter_breaker
        logger.info("=== SYSTEM MESSAGE ===")
        logger.info(system_prompt if system_prompt else "[None]")
        logger.info("=== USER MESSAGE ===")
        logger.info(prompt)
        
        def _do_stream_complete():
            return openai_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=messages,
                stream=True,
                max_tokens=1500
            )
            
        response = openrouter_breaker.call(_do_stream_complete)
        
        token_count = 0
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                token_count += 1
                yield delta
        duration_ms = (time.time() - start_time) * 1000.0
        record_latency("openrouter", duration_ms)
        # Estimate prompt tokens based on word count multiplier (1.33 tokens/word)
        prompt_words = len(prompt.split()) + len((system_prompt or "").split())
        prompt_est = int(prompt_words * 1.33)
        record_token_usage(prompt_est, token_count)
    except Exception as e:
        logger.error(f"OpenRouter streaming completion failed: {e}")
        yield f"\n[Error during generation: {e}]"

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
