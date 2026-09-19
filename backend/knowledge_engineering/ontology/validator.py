import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# This dictates which relationships are valid between specific Entity Types
# Format: {(SourceType, TargetType): [Allowed_Relationships...]}
# Using a simplified ruleset for now, but easily expandable.
ALLOWED_RELATIONS_BY_TYPE = {
    # Person -> *
    ("Person", "Equipment"): ["INSPECTS", "MAINTAINS", "OPERATES", "MANAGES", "RESPONSIBLE_FOR", "RELATED_TO", "KNOWLEDGE_OWNER"],
    ("Person", "Asset"): ["INSPECTS", "MAINTAINS", "OPERATES", "MANAGES", "RESPONSIBLE_FOR", "RELATED_TO", "KNOWLEDGE_OWNER"],
    ("Person", "Document"): ["AUTHORED_BY", "RELATED_TO", "REFERENCES"],
    ("Person", "Procedure"): ["AUTHORED_BY", "RELATED_TO", "REFERENCES", "OWNS"],
    ("Person", "Incident"): ["REPORTED_BY", "INVESTIGATED", "INVOLVED_IN", "RELATED_TO"],
    
    # Equipment -> *
    ("Equipment", "Equipment"): ["CONNECTED_TO", "FEEDS", "SUPPLIES", "DEPENDS_ON", "PART_OF", "RELATED_TO"],
    ("Equipment", "Asset"): ["CONNECTED_TO", "FEEDS", "SUPPLIES", "DEPENDS_ON", "PART_OF", "RELATED_TO"],
    ("Equipment", "Incident"): ["INVOLVED_IN", "CAUSED", "FAILED_AT", "RELATED_TO", "AFFECTED_BY"],
    ("Equipment", "Person"): ["MAINTAINED_BY", "OPERATED_BY", "INSPECTED_BY", "RELATED_TO", "OWNS"],
    ("Equipment", "Procedure"): ["HAS_PROCEDURE", "RELATED_TO", "REFERENCES"],
    
    # Asset -> *
    ("Asset", "Asset"): ["CONNECTED_TO", "FEEDS", "SUPPLIES", "DEPENDS_ON", "PART_OF", "RELATED_TO"],
    ("Asset", "Equipment"): ["CONNECTED_TO", "FEEDS", "SUPPLIES", "DEPENDS_ON", "PART_OF", "RELATED_TO"],
    ("Asset", "Incident"): ["INVOLVED_IN", "CAUSED", "FAILED_AT", "RELATED_TO", "AFFECTED_BY"],
    ("Asset", "Person"): ["MAINTAINED_BY", "OPERATED_BY", "INSPECTED_BY", "RELATED_TO"],
    
    # Incident -> *
    ("Incident", "Equipment"): ["AFFECTS", "RELATED_TO", "CAUSED_BY", "OCCURRED_ON"],
    ("Incident", "Person"): ["REPORTED_BY", "INVESTIGATED_BY", "RELATED_TO"],
    ("Incident", "Document"): ["DOCUMENTED_IN", "RELATED_TO"],
    
    # Document / Procedure -> *
    ("Document", "Equipment"): ["APPLIES_TO", "GOVERNS", "RELATED_TO"],
    ("Procedure", "Equipment"): ["APPLIES_TO", "GOVERNS", "RELATED_TO"],
    ("Document", "Person"): ["AUTHORED_BY", "RELATED_TO"],
    ("Procedure", "Person"): ["AUTHORED_BY", "RELATED_TO"],
}

def is_valid_relation(source_type: str, target_type: str, rel_type: str) -> bool:
    """
    Checks if a relationship is permitted between two specific entity types.
    """
    allowed = ALLOWED_RELATIONS_BY_TYPE.get((source_type, target_type))
    if not allowed:
        # If we haven't strictly defined the pairing, fallback to permissive for now,
        # but in a strict ontology we might return False.
        # Let's be semi-strict: allow RELATED_TO, but block everything else unless defined.
        return rel_type == "RELATED_TO"
    
    return rel_type in allowed

def validate_relationships(extracted_rels: List[Dict[str, Any]], extracted_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validates that extracted relationships conform to the ontology rules for their specific entity types.
    Drops invalid relationships to prevent garbage edges in the graph.
    """
    # Build a lookup map for entity types
    entity_types = {}
    for ent in extracted_entities:
        # Entity names might have aliases, map all of them to the type
        etype = ent.get("type", "Entity")
        entity_types[ent["name"]] = etype
        for alias in ent.get("aliases", []):
            entity_types[alias] = etype
            
    valid_rels = []
    
    for rel in extracted_rels:
        source_name = rel.get("source", "")
        target_name = rel.get("target", "")
        rel_type = rel.get("type", "RELATED_TO")
        
        source_type = entity_types.get(source_name, "Entity")
        target_type = entity_types.get(target_name, "Entity")
        
        # If it's literally UNKNOWN_RELATIONSHIP from older prompts, drop it completely.
        if rel_type == "UNKNOWN_RELATIONSHIP":
            logger.warning(f"Validation: Dropped UNKNOWN_RELATIONSHIP edge '{source_name}' -> '{target_name}'")
            continue
            
        if is_valid_relation(source_type, target_type, rel_type):
            valid_rels.append(rel)
        else:
            logger.warning(f"Validation: Dropped invalid ontology edge '{source_name}' ({source_type}) -[{rel_type}]-> '{target_name}' ({target_type})")
            
    return valid_rels
