import json
import statistics
from typing import Dict, Any

def run_compliance_eval(dataset_path: str, tenant_id: str) -> Dict[str, Any]:
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    cases = dataset.get("compliance_cases", [])
    if not cases:
        return {"error": "No compliance cases found"}
        
    metrics = {
        "classification_accuracy": [],
        "evidence_quality": []
    }
    
    # Normally we would mock the document context retrieval, but since we want to evaluate 
    # the LLM compliance analysis step directly, we will directly call the evaluate_compliance_node
    # in the compliance agent workflow.
    from backend.agents.compliance_agent import evaluate_compliance_node, ComplianceState
    
    for case in cases:
        doc_text = case["document_text"]
        
        # We need mock regulations to feed the node
        # In actual usage we would fetch these from DB based on regulation_scope, but for eval
        # we can inject standard test requirements.
        test_regs = [
            {"name": "osha-1", "requirement": "Must have pressure relief valves installed on all vessels."},
            {"name": "osha-2", "requirement": "Requires annual hydrostatic testing."},
            {"name": "iso-1", "requirement": "Emergency stop buttons must be hardwired."}
        ]
        
        # Create a mock state
        state = {
            "document_id": "999",
            "tenant_id": tenant_id,
            "regulation_scope": case["regulation_scope"],
            "document_text": doc_text,
            "document_context": [doc_text],
            "applicable_regulations": test_regs,
            "evaluations": [],
            "overall_risk": "",
            "compliance_score": 0,
            "compliant_count": 0,
            "gap_count": 0
        }
        
        try:
            result = evaluate_compliance_node(state)
            evals = result.get("report", {}).get("evaluations", [])
            
            # Evaluate Accuracy
            correct = 0
            total = len(test_regs)
            good_evidence = 0
            
            for e in evals:
                clause_id = e.get("clause_id", "")
                status = e.get("status", "")
                evidence = e.get("evidence_excerpt", "")
                
                if clause_id in case["expected_compliant_clauses"]:
                    if status == "COMPLIANT":
                        correct += 1
                    if evidence and len(evidence) > 10:
                        good_evidence += 1
                elif clause_id in case["expected_non_compliant_clauses"]:
                    if status == "NON_COMPLIANT":
                        correct += 1
                        
            metrics["classification_accuracy"].append(correct / total if total > 0 else 0)
            metrics["evidence_quality"].append(good_evidence / len(case["expected_compliant_clauses"]) if case["expected_compliant_clauses"] else 1.0)
            
        except Exception as e:
            print(f"Compliance eval failed for case: {e}")
            metrics["classification_accuracy"].append(0)
            metrics["evidence_quality"].append(0)
            
    return {
        "classification_accuracy": statistics.mean(metrics["classification_accuracy"]) if metrics["classification_accuracy"] else 0,
        "evidence_quality": statistics.mean(metrics["evidence_quality"]) if metrics["evidence_quality"] else 0
    }
