import logging
from backend.config import get_settings
from backend.llm.base import LLMProvider
from backend.llm.providers.ollama import OllamaProvider
from backend.llm.providers.openai_compatible import OpenAICompatibleProvider
from backend.llm.providers.anthropic import AnthropicProvider

logger = logging.getLogger(__name__)

def get_provider_instance(provider_name: str, model_name: str) -> LLMProvider:
    """
    Factory function to instantiate the correct LLMProvider.
    """
    settings = get_settings()
    provider_name = provider_name.lower()

    if provider_name == "ollama":
        if not settings.OLLAMA_ENABLED:
            logger.warning("Requested Ollama but it is disabled. Attempting fallback if possible.")
        return OllamaProvider(base_url=settings.OLLAMA_URL, model=model_name)
        
    elif provider_name == "openrouter":
        return OpenAICompatibleProvider(
            api_key=settings.OPENROUTER_API_KEY, 
            model=model_name, 
            base_url="https://openrouter.ai/api/v1"
        )
        
    elif provider_name == "openai":
        return OpenAICompatibleProvider(
            api_key=settings.OPENAI_API_KEY, 
            model=model_name, 
            base_url="https://api.openai.com/v1"
        )
        
    elif provider_name == "groq":
        return OpenAICompatibleProvider(
            api_key=settings.GROQ_API_KEY, 
            model=model_name, 
            base_url="https://api.groq.com/openai/v1"
        )
        
    elif provider_name == "gemini":
        return OpenAICompatibleProvider(
            api_key=settings.GEMINI_API_KEY, 
            model=model_name, 
            base_url="https://generativelanguage.googleapis.com/v1beta/openai"
        )
        
    elif provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=model_name
        )
        
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
