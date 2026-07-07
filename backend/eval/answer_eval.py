import json
import statistics
from typing import Dict, Any

from backend.agents.copilot_agent import copilot_agent

def run_answer_eval(dataset_path: str, tenant_id: str) -> Dict[str, Any]:
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    cases = dataset.get("copilot_qa_pairs", [])
    if not cases:
        return {"error": "No QA pairs found"}
        
    metrics = {
        "groundedness": [],
        "citation_coverage": [],
        "hallucination_rate": [],
        "entity_recall": [],
        "keyword_hit_rate": []
    }
    
    for case in cases:
        query = case["query"]
        must_cite = case.get("must_cite_entities", [])
        must_not_hallucinate = case.get("must_not_hallucinate", [])
        expected_kws = case.get("expected_answer_keywords", [])
        
        # Run agent via stream
        stream = copilot_agent.run_stream(query, history=[], tenant_id=tenant_id)
        
        full_response = ""
        citations = []
        for chunk in stream:
            if isinstance(chunk, dict):
                if chunk.get("type") == "citations":
                    citations = chunk.get("data", [])
            elif isinstance(chunk, str):
                full_response += chunk
                
        # The LLM outputs a JSON string for structured schema
        try:
            import re
            json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', full_response, re.DOTALL)
            if json_block:
                parsed = json.loads(json_block.group(1))
            else:
                parsed = json.loads(full_response)
            answer = parsed.get("summary", "").lower() + " " + parsed.get("reasoning_chain", "").lower()
        except:
            answer = full_response.lower()
        
        # 1. Groundedness (simplified heuristic: how much of the answer nouns are in citations)
        # We will use keyword overlap as a proxy for groundedness to avoid LLM-as-judge
        # If the answer uses expected_kws, are they in the chunks?
        if expected_kws:
            cited_text = " ".join([c.get("text", "") for c in citations]).lower()
            grounded_hits = 0
            for kw in expected_kws:
                if kw in answer and kw in cited_text:
                    grounded_hits += 1
            ans_kws_used = sum(1 for kw in expected_kws if kw in answer)
            metrics["groundedness"].append(grounded_hits / ans_kws_used if ans_kws_used else 1.0)
            
        # 2. Citation coverage
        metrics["citation_coverage"].append(1.0 if citations else 0.0)
        
        # 3. Hallucination rate
        if must_not_hallucinate:
            hallucinations = sum(1 for h in must_not_hallucinate if h.lower() in answer)
            metrics["hallucination_rate"].append(hallucinations / len(must_not_hallucinate))
            
        # 4. Entity recall
        if must_cite:
            cited = 0
            for e in must_cite:
                if e.lower() in answer:
                    cited += 1
            metrics["entity_recall"].append(cited / len(must_cite))
            
        # 5. Keyword hit rate
        if expected_kws:
            hits = sum(1 for kw in expected_kws if kw.lower() in answer)
            metrics["keyword_hit_rate"].append(hits / len(expected_kws))
            
    return {
        "groundedness": statistics.mean(metrics["groundedness"]) if metrics["groundedness"] else 0,
        "citation_coverage": statistics.mean(metrics["citation_coverage"]) if metrics["citation_coverage"] else 0,
        "hallucination_rate": statistics.mean(metrics["hallucination_rate"]) if metrics["hallucination_rate"] else 0,
        "entity_recall": statistics.mean(metrics["entity_recall"]) if metrics["entity_recall"] else 0,
        "keyword_hit_rate": statistics.mean(metrics["keyword_hit_rate"]) if metrics["keyword_hit_rate"] else 0
    }
