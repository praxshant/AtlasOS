import json
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.db.postgres import Entity
from backend.utils.llm_client import structured_complete

logger = logging.getLogger(__name__)

# Valid entity types and relationship types
VALID_LABELS = {
    "Asset", "Incident", "Person", "Procedure", "Regulation", 
    "FailureMode", "Equipment", "LessonLearned", "AuditFinding"
}

VALID_RELATIONSHIPS = {
    "OCCURRED_ON", "MAINTAINED_BY", "REPORTED_BY", "CAUSED_BY", 
    "PREVENTS", "VIOLATES", "COMPLIES_WITH", "RELATED_TO", 
    "RESULTED_IN", "APPLIES_TO", "LEARNED_FROM"
}

def build_extraction_prompt(chunk_text: str) -> str:
    """
    Builds the system and user prompt for LLM entity & relation extraction.
    """
    prompt = f"""
    Analyze the following industrial operations text chunk and extract all entities and relationships.
    
    Text chunk:
    ---
    {chunk_text}
    ---
    
    Instructions:
    1. Extract all key entities. Each entity must have:
       - name: A canonical, specific name (e.g. "Pump P-104", "OSHA 1910.119", "Ramesh Kumar", "Seal Leak"). Deduplicate names to their standard form.
       - type: Must be EXACTLY one of: {list(VALID_LABELS)}
       - properties: Key-value dictionary containing details like location, code, severity, department, date, or description.
       - confidence: float between 0.0 and 1.0.
       
    2. Extract all direct relationships between the extracted entities. Each relationship must have:
       - source: Name of the source entity.
       - target: Name of the target entity.
       - type: Must be EXACTLY one of: {list(VALID_RELATIONSHIPS)}
       - confidence: float between 0.0 and 1.0.
       
    Return your response strictly in the following JSON format without any other markdown formatting or conversational filler:
    {{
      "entities": [
        {{ "name": "Pump P-104", "type": "Asset", "properties": {{ "location": "Unit 3", "type": "Centrifugal" }}, "confidence": 0.95 }}
      ],
      "relationships": [
        {{ "source": "Pump P-104", "target": "Seal Leak", "type": "RELATED_TO", "confidence": 0.90 }}
      ]
    }}
    """
    return prompt

def extract_entities_and_relationships(chunk_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Sends chunk text to LLM and parses the JSON response into entities and relationships.
    """
    prompt = build_extraction_prompt(chunk_text)
    system_prompt = "You are a senior process safety and industrial operations analyst. Extract entities and relationships in strict JSON format."
    
    try:
        data = structured_complete(prompt, system_prompt=system_prompt)
        
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])
        
        # Validate entity types and relationship types
        valid_entities = []
        for e in entities:
            if e.get("type") in VALID_LABELS and e.get("name"):
                valid_entities.append(e)
            else:
                logger.warning(f"Skipping invalid entity: {e}")
                
        valid_relationships = []
        for r in relationships:
            if r.get("type") in VALID_RELATIONSHIPS and r.get("source") and r.get("target"):
                valid_relationships.append(r)
            else:
                logger.warning(f"Skipping invalid relationship: {r}")
                
        return valid_entities, valid_relationships
        
    except Exception as e:
        logger.error(f"Failed to extract entities/relationships from chunk: {e}")
        return [], []

def deduplicate_and_save_entities(db: Session, entities: List[Dict[str, Any]], doc_id: int, tenant_id: str) -> Dict[Tuple[str, str], int]:
    """
    Deduplicates and saves entities to PostgreSQL.
    Returns a mapping of (entity_name, entity_type) -> postgres_entity_id.
    """
    entity_mapping = {}
    
    for entity_data in entities:
        name = entity_data["name"].strip()
        etype = entity_data["type"]
        confidence = entity_data.get("confidence", 1.0)
        
        # Look for case-insensitive match of name and exact match of type and tenant
        existing_entity = db.query(Entity).filter(
            Entity.tenant_id == tenant_id,
            Entity.canonical_name.ilike(name),
            Entity.entity_type == etype
        ).first()
        
        if existing_entity:
            entity_mapping[(name.lower(), etype)] = existing_entity.id
            # Optionally update confidence or doc provenance if needed
        else:
            new_entity = Entity(
                tenant_id=tenant_id,
                canonical_name=name,
                entity_type=etype,
                confidence=confidence,
                source_doc_id=doc_id
            )
            db.add(new_entity)
            db.flush() # Populate the ID
            entity_mapping[(name.lower(), etype)] = new_entity.id
            
    return entity_mapping

def batch_extract_entities(texts: List[str], tenant_id: str = None) -> List[Dict[str, Any]]:
    """
    Extracts entities and relationships for a list of texts.
    """
    results = []
    for text in texts:
        entities, relationships = extract_entities_and_relationships(text)
        results.append({
            "entities": entities,
            "relationships": relationships
        })
    return results

