import time
import json
import statistics
from typing import Dict, Any

def run_latency_eval(dataset_path: str, tenant_id: str) -> Dict[str, Any]:
    # Most latency stats can be aggregated from the other modules if we return them,
    # or we can do a couple quick passes here for pure latency measurement.
    # To keep it isolated, we'll do a quick pass over a couple of functions.
    
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    metrics = {
        "retrieval_ms": [],
        "extraction_ms": [],
        "copilot_total_ms": [],
        "graph_query_ms": []
    }
    
    from backend.retrieval.hybrid_retriever import hybrid_retriever
    from backend.ingestion.entity_extractor import extract_entities_and_relationships
    from backend.agents.copilot_agent import copilot_agent
    from backend.graph.neo4j_client import neo4j_client
    
    # 1. Retrieval Latency
    for q in dataset.get("retrieval_queries", []):
        start = time.perf_counter()
        hybrid_retriever.retrieve(q["query"], tenant_id=tenant_id, query_type=q.get("query_type", "general"))
        metrics["retrieval_ms"].append((time.perf_counter() - start) * 1000)
        
    # 2. Extraction Latency
    for case in dataset.get("entity_extraction_cases", []):
        start = time.perf_counter()
        extract_entities_and_relationships(case["text"])
        metrics["extraction_ms"].append((time.perf_counter() - start) * 1000)
        
    if dataset.get("copilot_qa_pairs"):
        case = dataset["copilot_qa_pairs"][0]
        start = time.perf_counter()
        stream = copilot_agent.run_stream(case["query"], history=[], tenant_id=tenant_id)
        for _ in stream:
            pass
        metrics["copilot_total_ms"].append((time.perf_counter() - start) * 1000)
        
    # 4. Graph Query Latency
    start = time.perf_counter()
    neo4j_client.run_query("MATCH (n:Entity {tenant_id: $t}) RETURN count(n)", {"t": tenant_id})
    metrics["graph_query_ms"].append((time.perf_counter() - start) * 1000)
    
    def get_p50(data):
        return statistics.median(data) if data else 0
        
    def get_p95(data):
        if not data: return 0
        if len(data) == 1: return data[0]
        try:
            return statistics.quantiles(data, n=20)[18]
        except:
            return data[-1]
            
    return {
        "retrieval_p50_ms": get_p50(metrics["retrieval_ms"]),
        "retrieval_p95_ms": get_p95(metrics["retrieval_ms"]),
        "extraction_per_chunk_ms": get_p50(metrics["extraction_ms"]),
        "copilot_total_ms": get_p50(metrics["copilot_total_ms"]),
        "graph_query_p50_ms": get_p50(metrics["graph_query_ms"])
    }
