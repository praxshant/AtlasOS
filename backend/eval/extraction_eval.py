import json
import statistics
from typing import Dict, Any

from backend.ingestion.entity_extractor import extract_entities_and_relationships

def _fuzzy_match(s1: str, s2: str) -> bool:
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()
    if s1 == s2:
        return True
    if s1 in s2 or s2 in s1:
        return True
    return False

def run_extraction_eval(dataset_path: str) -> Dict[str, Any]:
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    cases = dataset.get("entity_extraction_cases", [])
    if not cases:
        return {"error": "No entity extraction cases found"}
        
    metrics = {
        "entity_precision": [],
        "entity_recall": [],
        "rel_precision": [],
        "rel_recall": [],
        "type_accuracy": [],
        "ontology_classification_rate": []
    }
    
    for case in cases:
        text = case["text"]
        expected_entities = case.get("expected_entities", [])
        expected_relationships = case.get("expected_relationships", [])
        
        extracted_entities, extracted_relationships = extract_entities_and_relationships(text)
        
        # Entity Metrics
        if expected_entities:
            true_positives = 0
            correct_types = 0
            for exp_e in expected_entities:
                matched = False
                for ext_e in extracted_entities:
                    if _fuzzy_match(exp_e["name"], ext_e["name"]):
                        matched = True
                        if exp_e["type"] == ext_e["type"]:
                            correct_types += 1
                        break
                if matched:
                    true_positives += 1
                    
            recall = true_positives / len(expected_entities)
            precision = true_positives / len(extracted_entities) if extracted_entities else 0
            
            metrics["entity_recall"].append(recall)
            metrics["entity_precision"].append(precision)
            if true_positives > 0:
                metrics["type_accuracy"].append(correct_types / true_positives)
                
        # Ontology metrics
        if extracted_entities:
            with_ontology = sum(1 for e in extracted_entities if "subtype" in e or "subclass" in e)
            metrics["ontology_classification_rate"].append(with_ontology / len(extracted_entities))
            
        # Relationship Metrics
        if expected_relationships:
            true_positives = 0
            for exp_r in expected_relationships:
                matched = False
                for ext_r in extracted_relationships:
                    if _fuzzy_match(exp_r["source"], ext_r["source"]) and \
                       _fuzzy_match(exp_r["target"], ext_r["target"]) and \
                       exp_r["type"] == ext_r["type"]:
                        matched = True
                        break
                if matched:
                    true_positives += 1
                    
            recall = true_positives / len(expected_relationships)
            precision = true_positives / len(extracted_relationships) if extracted_relationships else 0
            
            metrics["rel_recall"].append(recall)
            metrics["rel_precision"].append(precision)
            
    def f1(p, r):
        if p + r == 0:
            return 0
        return 2 * (p * r) / (p + r)
        
    ep = statistics.mean(metrics["entity_precision"]) if metrics["entity_precision"] else 0
    er = statistics.mean(metrics["entity_recall"]) if metrics["entity_recall"] else 0
    rp = statistics.mean(metrics["rel_precision"]) if metrics["rel_precision"] else 0
    rr = statistics.mean(metrics["rel_recall"]) if metrics["rel_recall"] else 0

    return {
        "entity_precision": ep,
        "entity_recall": er,
        "entity_f1": f1(ep, er),
        "relationship_precision": rp,
        "relationship_recall": rr,
        "relationship_f1": f1(rp, rr),
        "type_accuracy": statistics.mean(metrics["type_accuracy"]) if metrics["type_accuracy"] else 0,
        "ontology_classification_rate": statistics.mean(metrics["ontology_classification_rate"]) if metrics["ontology_classification_rate"] else 0
    }
