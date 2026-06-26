import contextvars
import logging
from typing import Optional

# Context variable to hold the correlation ID for the current request context
correlation_id_var = contextvars.ContextVar("correlation_id", default="")

class CorrelationIdFormatter(logging.Formatter):
    """
    Custom formatter that injects correlation_id into the log format.
    """
    def format(self, record):
        record.correlation_id = correlation_id_var.get() or "SYSTEM"
        return super().format(record)

def setup_logging(level: int = logging.INFO):
    """
    Sets up the structured logging handler with our custom correlation ID formatter.
    """
    handler = logging.StreamHandler()
    formatter = CorrelationIdFormatter(
        "%(asctime)s [%(levelname)s] [Corr-ID: %(correlation_id)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    
    root = logging.getLogger()
    # Clear existing handlers to prevent duplicate logs
    for h in root.handlers[:]:
        root.removeHandler(h)
        
    root.addHandler(handler)
    root.setLevel(level)

def set_correlation_id(corr_id: str):
    correlation_id_var.set(corr_id)

def get_correlation_id() -> str:
    return correlation_id_var.get()
