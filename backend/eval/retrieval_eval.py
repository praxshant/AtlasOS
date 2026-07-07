import json
import os
import time
import statistics
from typing import Dict, Any

from backend.retrieval.hybrid_retriever import hybrid_retriever
from backend.vector.qdrant_client import qdrant_client

def run_retrieval_eval(dataset_path: str, tenant_id: str) -> Dict[str, Any]:
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    queries = dataset.get("retrieval_queries", [])
    if not queries:
        return {"error": "No retrieval queries found in dataset"}
        
    metrics = {
        "hybrid_recall_at_3": [],
        "hybrid_recall_at_5": [],
        "hybrid_recall_at_8": [],
        "hybrid_mrr": [],
        "bm25_recall_at_5": [],
        "dense_recall_at_5": [],
        "latency_ms": []
    }
    
    for q in queries:
        query_text = q["query"]
        expected_kws = set(kw.lower() for kw in q["expected_keywords"])
        
        # 1. Latency & Hybrid Retrieval
        start = time.perf_counter()
        hybrid_results = hybrid_retriever.retrieve(query_text, tenant_id=tenant_id, query_type=q.get("query_type", "general"))
        latency = (time.perf_counter() - start) * 1000
        metrics["latency_ms"].append(latency)
        
        # 2. Individual retrievals for comparison
        bm25_results = hybrid_retriever.bm25_retrieval(query_text, tenant_id=tenant_id, top_k=20)
        dense_results = qdrant_client.similarity_search("document_chunks", query_text, top_k=20, tenant_id=tenant_id)
        
        def calc_recall(results, top_k):
            found_kws = set()
            for r in results[:top_k]:
                text = r.get("text", "").lower()
                for kw in expected_kws:
                    if kw in text:
                        found_kws.add(kw)
            if not expected_kws:
                return 1.0
            return len(found_kws) / len(expected_kws)
            
        def calc_mrr(results):
            for i, r in enumerate(results):
                text = r.get("text", "").lower()
                if any(kw in text for kw in expected_kws):
                    return 1.0 / (i + 1)
            return 0.0

        metrics["hybrid_recall_at_3"].append(calc_recall(hybrid_results, 3))
        metrics["hybrid_recall_at_5"].append(calc_recall(hybrid_results, 5))
        metrics["hybrid_recall_at_8"].append(calc_recall(hybrid_results, 8))
        metrics["hybrid_mrr"].append(calc_mrr(hybrid_results))
        metrics["bm25_recall_at_5"].append(calc_recall(bm25_results, 5))
        metrics["dense_recall_at_5"].append(calc_recall(dense_results, 5))

    return {
        "recall_at_3": statistics.mean(metrics["hybrid_recall_at_3"]) if metrics["hybrid_recall_at_3"] else 0,
        "recall_at_5": statistics.mean(metrics["hybrid_recall_at_5"]) if metrics["hybrid_recall_at_5"] else 0,
        "recall_at_8": statistics.mean(metrics["hybrid_recall_at_8"]) if metrics["hybrid_recall_at_8"] else 0,
        "mrr": statistics.mean(metrics["hybrid_mrr"]) if metrics["hybrid_mrr"] else 0,
        "bm25_recall_at_5": statistics.mean(metrics["bm25_recall_at_5"]) if metrics["bm25_recall_at_5"] else 0,
        "dense_recall_at_5": statistics.mean(metrics["dense_recall_at_5"]) if metrics["dense_recall_at_5"] else 0,
        "hybrid_recall_at_5": statistics.mean(metrics["hybrid_recall_at_5"]) if metrics["hybrid_recall_at_5"] else 0,
        "rerank_lift": (statistics.mean(metrics["hybrid_recall_at_5"]) - max(statistics.mean(metrics["bm25_recall_at_5"]), statistics.mean(metrics["dense_recall_at_5"]))) if metrics["hybrid_recall_at_5"] else 0,
        "latency_p50_ms": statistics.median(metrics["latency_ms"]) if metrics["latency_ms"] else 0,
        "latency_p95_ms": statistics.quantiles(metrics["latency_ms"], n=20)[18] if len(metrics["latency_ms"]) > 1 else (metrics["latency_ms"][0] if metrics["latency_ms"] else 0)
    }
