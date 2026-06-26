"""
Circuit Breaker pattern implementation for AtlasOS infrastructure subsystems.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Too many failures, requests are rejected immediately
- HALF_OPEN: Recovery testing, limited requests allowed
"""

import time
import logging
import threading
from typing import Callable, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is OPEN."""
    def __init__(self, name: str, recovery_time: float):
        self.name = name
        self.recovery_time = recovery_time
        super().__init__(f"Circuit breaker '{name}' is OPEN. Recovery in {recovery_time:.1f}s")


class CircuitBreaker:
    """
    Generic circuit breaker that wraps calls to external services.
    
    Usage:
        breaker = CircuitBreaker("neo4j", failure_threshold=5, recovery_timeout=30)
        try:
            result = breaker.call(my_function, arg1, arg2)
        except CircuitOpenError:
            # Service is down, use fallback
            result = fallback_value
    """
    
    def __init__(self, name: str, failure_threshold: int = 5, 
                 recovery_timeout: float = 30.0, half_open_max: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()
        
    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(f"Circuit breaker '{self.name}' transitioning from OPEN to HALF_OPEN")
            return self._state
    
    @property
    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN
    
    def get_status(self) -> dict:
        """Returns current circuit breaker status for monitoring."""
        state = self.state
        return {
            "name": self.name,
            "state": state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "recovery_time_remaining": max(0, self.recovery_timeout - (time.time() - self._last_failure_time)) if state == CircuitState.OPEN else 0
        }
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.
        
        Raises CircuitOpenError if the circuit is OPEN.
        """
        current_state = self.state
        
        if current_state == CircuitState.OPEN:
            remaining = self.recovery_timeout - (time.time() - self._last_failure_time)
            raise CircuitOpenError(self.name, max(0, remaining))
        
        if current_state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.half_open_max:
                    raise CircuitOpenError(self.name, self.recovery_timeout)
                self._half_open_calls += 1
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise
    
    def _on_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                # If enough successes in half-open, close the circuit
                if self._success_count >= self.half_open_max:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(f"Circuit breaker '{self.name}' CLOSED (recovered)")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0
                self._success_count += 1
    
    def _on_failure(self, error: Exception):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker '{self.name}' back to OPEN after HALF_OPEN failure: {error}")
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.error(f"Circuit breaker '{self.name}' OPENED after {self._failure_count} failures: {error}")
    
    def reset(self):
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")


# --- Global Circuit Breaker Instances ---

neo4j_breaker = CircuitBreaker("neo4j", failure_threshold=5, recovery_timeout=30)
qdrant_breaker = CircuitBreaker("qdrant", failure_threshold=5, recovery_timeout=30)
openrouter_breaker = CircuitBreaker("openrouter", failure_threshold=3, recovery_timeout=60)
postgres_breaker = CircuitBreaker("postgres", failure_threshold=5, recovery_timeout=30)

def get_all_breaker_statuses() -> dict:
    """Returns status of all circuit breakers for the health endpoint."""
    return {
        "neo4j": neo4j_breaker.get_status(),
        "qdrant": qdrant_breaker.get_status(),
        "openrouter": openrouter_breaker.get_status(),
        "postgres": postgres_breaker.get_status(),
    }
