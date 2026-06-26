import time
import logging
import threading
from typing import Dict, Any

from backend.utils.circuit_breaker import get_all_breaker_statuses
from backend.db.postgres import SessionLocal
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client
from backend.utils.llm_client import get_client as get_llm_client

logger = logging.getLogger(__name__)

class HealthMonitor:
    def __init__(self):
        self._running = False
        self._thread = None
        self._status_cache = {}
        self._last_check_time = 0

    def start(self, interval_seconds: int = 30):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, args=(interval_seconds,), daemon=True)
        self._thread.start()
        logger.info(f"Health monitor started (interval: {interval_seconds}s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            logger.info("Health monitor stopped")

    def _monitor_loop(self, interval: int):
        while self._running:
            try:
                self.check_all()
            except Exception as e:
                logger.error(f"Health monitor loop error: {e}")
            time.sleep(interval)

    def check_all(self) -> Dict[str, Any]:
        """Runs health checks on all subsystems and updates cache."""
        status = {
            "timestamp": time.time(),
            "services": {},
            "circuit_breakers": get_all_breaker_statuses()
        }

        # 1. Postgres
        try:
            start_t = time.time()
            db = SessionLocal()
            db.execute("SELECT 1")
            db.close()
            status["services"]["postgres"] = {
                "status": "healthy",
                "latency_ms": round((time.time() - start_t) * 1000, 2)
            }
        except Exception as e:
            status["services"]["postgres"] = {"status": "unhealthy", "error": str(e)}

        # 2. Neo4j
        try:
            start_t = time.time()
            driver = neo4j_client.get_driver()
            if driver:
                driver.verify_connectivity()
                status["services"]["neo4j"] = {
                    "status": "healthy",
                    "latency_ms": round((time.time() - start_t) * 1000, 2)
                }
            else:
                status["services"]["neo4j"] = {"status": "unhealthy", "error": "Driver not initialized"}
        except Exception as e:
            status["services"]["neo4j"] = {"status": "unhealthy", "error": str(e)}

        # 3. Qdrant
        try:
            start_t = time.time()
            client = qdrant_client.get_client()
            if client:
                client.get_collections()
                status["services"]["qdrant"] = {
                    "status": "healthy",
                    "latency_ms": round((time.time() - start_t) * 1000, 2)
                }
            else:
                status["services"]["qdrant"] = {"status": "unhealthy", "error": "Client not initialized"}
        except Exception as e:
            status["services"]["qdrant"] = {"status": "unhealthy", "error": str(e)}

        # 4. OpenRouter (API Key check only, no real completion to save costs)
        try:
            start_t = time.time()
            llm = get_llm_client()
            if llm:
                status["services"]["openrouter"] = {
                    "status": "healthy",
                    "latency_ms": round((time.time() - start_t) * 1000, 2)
                }
            else:
                status["services"]["openrouter"] = {"status": "unhealthy", "error": "Client not initialized"}
        except Exception as e:
            status["services"]["openrouter"] = {"status": "unhealthy", "error": str(e)}

        self._status_cache = status
        self._last_check_time = status["timestamp"]
        return status

    def get_latest_status(self) -> Dict[str, Any]:
        """Returns the most recent health status."""
        if not self._status_cache or (time.time() - self._last_check_time > 60):
            # Cache is stale or empty, run synchronous check
            return self.check_all()
        return self._status_cache

health_monitor = HealthMonitor()
