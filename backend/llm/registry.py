import os
import yaml
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ModelRegistry:
    def __init__(self, config_path: str = None):
        if not config_path:
            config_path = os.path.join(os.path.dirname(__file__), "registry.yaml")
        self.config_path = config_path
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load model registry from {self.config_path}: {e}")
            return {}

    def get_providers_for_task(self, task: str) -> List[Dict[str, str]]:
        """
        Returns a combined list of preferred and fallback providers for a task.
        Each item is a dict with 'provider' and 'model'.
        """
        task_config = self.registry.get(task, {})
        preferred = task_config.get("preferred", [])
        fallback = task_config.get("fallback", [])
        return preferred + fallback

registry = ModelRegistry()
