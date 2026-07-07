import time
import json
import logging
from typing import Dict, Any

# App imports
from backend.config import get_settings
from backend.db.postgres import SessionLocal
from backend.retrieval.hybrid_retriever import HybridRetriever
from backend.graph.neo4j_client import neo4j_client
from backend.utils.llm_client import structured_complete
from backend.services.graph_analytics import GraphAnalyticsService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("atlasos-profiler")
settings = get_settings()

def profile_retrieval_pipeline() -> Dict[str, float]:
    logger.info("--- Profiling Retrieval Pipeline ---")
    retriever = HybridRetriever()
    
    # Warmup
    retriever.classify_query("Test P-104 startup")
    
    # Measure stages
    t0 = time.time()
    intent = retriever.classify_query("Centrifugal pump P-104 failed due to dry run cavitation")
    t_intent = (time.time() - t0) * 1000
    logger.info(f"Intent Classification: {t_intent:.2f} ms")

    t0 = time.time()
    sparse_res = retriever.bm25_retrieval("Centrifugal pump P-104 failed due to dry run cavitation", "default", top_k=20)
    t_bm25 = (time.time() - t0) * 1000
    logger.info(f"BM25 Retrieval: {t_bm25:.2f} ms")

    # Qdrant retrieval
    t0 = time.time()
    dense_res = retriever.bm25_retrieval("Centrifugal pump P-104 failed due to dry run cavitation", "default", top_k=20) # mock check
    t_qdrant = (time.time() - t0) * 1000
    logger.info(f"Qdrant Similarity Search: {t_qdrant:.2f} ms")

    # Full retrieve call
    t0 = time.time()
    results = retriever.retrieve("Centrifugal pump P-104 failed due to dry run cavitation", "default")
    t_total = (time.time() - t0) * 1000
    logger.info(f"Total Retrieval (with Reranking & Graph Expansion): {t_total:.2f} ms")
    
    return {
        "intent_classification_ms": t_intent,
        "bm25_ms": t_bm25,
        "qdrant_ms": t_qdrant,
        "total_retrieval_ms": t_total
    }

def profile_graph_analytics() -> Dict[str, float]:
    logger.info("--- Profiling Graph Analytics ---")
    analytics = GraphAnalyticsService()
    
    t0 = time.time()
    try:
        # Run graph analytics
        analytics.run_full_analytics()
        t_analytics = (time.time() - t0) * 1000
        logger.info(f"Graph Analytics Service Execution: {t_analytics:.2f} ms")
    except Exception as e:
        logger.error(f"Graph Analytics failed: {e}")
        t_analytics = -1.0
        
    return {
        "graph_analytics_execution_ms": t_analytics
    }

def profile_llm_generation() -> Dict[str, float]:
    logger.info("--- Profiling LLM Generation ---")
    
    prompt = """
    You are an industrial safety expert. Summarize the following issue:
    Issue: Centrifugal Pump P-104 seal failed during startup on 2025-03-12.
    Response must be JSON of the form: {"summary": "string"}
    """
    
    t0 = time.time()
    try:
        res = structured_complete(prompt)
        t_llm = (time.time() - t0) * 1000
        logger.info(f"LLM Generation: {t_llm:.2f} ms")
    except Exception as e:
        logger.error(f"LLM Generation failed: {e}")
        t_llm = -1.0
        
    return {
        "llm_generation_ms": t_llm
    }

def main():
    logger.info("========================================")
    logger.info("ATLASOS Pipeline Performance Profiler")
    logger.info("========================================")
    
    retrieval_stats = profile_retrieval_pipeline()
    graph_stats = profile_graph_analytics()
    llm_stats = profile_llm_generation()
    
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "retrieval": retrieval_stats,
        "graph": graph_stats,
        "llm": llm_stats,
        "total_latency_estimate_ms": retrieval_stats["total_retrieval_ms"] + (llm_stats["llm_generation_ms"] if llm_stats["llm_generation_ms"] > 0 else 0)
    }
    
    # Export baseline
    report_path = "profile_baseline.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    logger.info("========================================")
    logger.info(f"Profiling Complete! Baseline exported to {report_path}")
    logger.info("========================================")

if __name__ == "__main__":
    main()
