import os
import json
import uuid
from datetime import datetime

from backend.eval.retrieval_eval import run_retrieval_eval
from backend.eval.extraction_eval import run_extraction_eval
from backend.eval.graph_eval import run_graph_eval
from backend.eval.answer_eval import run_answer_eval
from backend.eval.compliance_eval import run_compliance_eval
from backend.eval.rca_eval import run_rca_eval
from backend.eval.latency_eval import run_latency_eval

def main():
    print("========================================")
    print("AtlasOS Evaluation Suite")
    print("========================================")
    
    # We will use the e2e test tenant if possible, or a new random one
    # Since we are querying actual graph/vector DB, we might want to use a tenant
    # that has some data, or rely on whatever is there.
    # To get realistic graph metrics, we should query a tenant that has data.
    # We will assume "default" tenant has data if no other is provided.
    tenant_id = os.environ.get("EVAL_TENANT_ID", "default")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(base_dir, "datasets", "eval_dataset.json")
    results_dir = os.path.join(base_dir, "results")
    
    os.makedirs(results_dir, exist_ok=True)
    
    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.2",
    }
    
    print(f"\n[1/7] Running Retrieval Evaluation (Tenant: {tenant_id})...")
    report["retrieval"] = run_retrieval_eval(dataset_path, tenant_id)
    print(f"      Hybrid Recall@5: {report['retrieval'].get('hybrid_recall_at_5', 0):.2f}")
    
    print("\n[2/7] Running Entity Extraction Evaluation...")
    report["extraction"] = run_extraction_eval(dataset_path)
    print(f"      Entity F1: {report['extraction'].get('entity_f1', 0):.2f}")
    print(f"      Relationship F1: {report['extraction'].get('relationship_f1', 0):.2f}")
    
    print("\n[3/7] Running Graph Evaluation...")
    report["graph"] = run_graph_eval(tenant_id)
    print(f"      Total Nodes: {report['graph'].get('total_nodes', 0)}")
    print(f"      Total Edges: {report['graph'].get('total_edges', 0)}")
    
    print("\n[4/7] Running Copilot Answer Evaluation...")
    report["answer_quality"] = run_answer_eval(dataset_path, tenant_id)
    print(f"      Groundedness: {report['answer_quality'].get('groundedness', 0):.2f}")
    
    print("\n[5/7] Running Compliance Evaluation...")
    report["compliance"] = run_compliance_eval(dataset_path, tenant_id)
    print(f"      Classification Accuracy: {report['compliance'].get('classification_accuracy', 0):.2f}")
    
    print("\n[6/7] Running RCA Evaluation...")
    report["rca"] = run_rca_eval(dataset_path, tenant_id)
    print(f"      Root Cause Hit Rate: {report['rca'].get('root_cause_hit_rate', 0):.2f}")
    
    print("\n[7/7] Running Latency Evaluation...")
    report["latency"] = run_latency_eval(dataset_path, tenant_id)
    print(f"      Retrieval p50 (ms): {report['latency'].get('retrieval_p50_ms', 0):.2f}")
    
    # Save Report
    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(results_dir, f"eval_report_{timestamp_str}.json")
    
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"\n========================================")
    print(f"Evaluation Complete!")
    print(f"Report saved to: {report_path}")
    print(f"========================================")

if __name__ == "__main__":
    main()
