import json
import statistics
from typing import Dict, Any

from backend.agents.rca_agent import rca_agent

def run_rca_eval(dataset_path: str, tenant_id: str) -> Dict[str, Any]:
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    cases = dataset.get("rca_cases", [])
    if not cases:
        return {"error": "No RCA cases found"}
        
    metrics = {
        "root_cause_hit_rate": [],
        "avg_fault_tree_depth": [],
        "avg_corrective_actions": []
    }
    
    for case in cases:
        incident_description = case["incident_description"]
        expected_roots = case.get("expected_root_causes", [])
        expected_depth = case.get("expected_fault_tree_depth", 3)
        
        # Run agent
        result = rca_agent.run(incident_description=incident_description, tenant_id=tenant_id)
        
        # Parse output
        primary_cause = result.get("primary_cause", "").lower()
        fault_tree = result.get("fault_tree", [])
        actions = result.get("corrective_actions", [])
        
        # 1. Root cause hit rate
        hits = 0
        for r in expected_roots:
            in_fault_tree = False
            for node in fault_tree:
                text_to_check = node if isinstance(node, str) else node.get("description", "")
                if r.lower() in text_to_check.lower():
                    in_fault_tree = True
                    break
            
            if r.lower() in primary_cause or in_fault_tree:
                hits += 1
        metrics["root_cause_hit_rate"].append(hits / len(expected_roots) if expected_roots else 1.0)
        
        # 2. Fault tree depth
        metrics["avg_fault_tree_depth"].append(len(fault_tree))
        
        # 3. Corrective actions count
        metrics["avg_corrective_actions"].append(len(actions))
        
    return {
        "root_cause_hit_rate": statistics.mean(metrics["root_cause_hit_rate"]) if metrics["root_cause_hit_rate"] else 0,
        "avg_fault_tree_depth": statistics.mean(metrics["avg_fault_tree_depth"]) if metrics["avg_fault_tree_depth"] else 0,
        "avg_corrective_actions": statistics.mean(metrics["avg_corrective_actions"]) if metrics["avg_corrective_actions"] else 0
    }
