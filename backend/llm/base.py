from abc import ABC, abstractmethod
from typing import Generator, Optional, Dict, Any

class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers in the Enterprise AI Gateway.
    """
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Standard text completion returning a string."""
        
    @abstractmethod
    def structured(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000) -> Dict[str, Any]:
        """Structured text completion returning a parsed JSON dictionary."""

    @abstractmethod
    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        """Streaming text completion returning a token generator."""

    @abstractmethod
    def health_check(self) -> bool:
        """Returns True if the provider is currently reachable and healthy."""
