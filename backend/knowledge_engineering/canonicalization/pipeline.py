import re
import logging
from typing import List, Dict, Any

from backend.knowledge_engineering.canonicalization.resolver import find_similar_entity, store_canonical_entity_vector, _make_canonical_id

logger = logging.getLogger(__name__)

def normalize_entity_name(name: str) -> str:
    """
    Strips titles, role suffixes, whitespace, casing, punctuation.
    """
    name = name.strip()
    
    is_equipment_tag = bool(re.search(r'\b[A-Z]{1,4}-?\d{2,4}\b', name))
    
    if not is_equipment_tag:
        # Strip parenthetical role/title suffixes: "Elena Rostova (Test Lead)" -> "Elena Rostova"
        name = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()

        # Strip known role/title prefixes: "CEO Sarah Jenkins" -> "Sarah Jenkins"
        ROLE_PREFIXES = r'^(CEO|CTO|CFO|COO|VP|SVP|EVP|Dr\.?|Prof\.?|Mr\.?|Mrs\.?|Ms\.?|Eng\.?|Sr\.?|Jr\.?|' \
                        r'Senior|Junior|Lead|Principal|Director|Manager|Head of|Chief|Officer|Inspector|' \
                        r'Engineer|Technician|Analyst|Consultant|Supervisor|Operator)\s+'
        name = re.sub(ROLE_PREFIXES, '', name, flags=re.IGNORECASE).strip()
        
    name = re.sub(r'\s+', ' ', name)
    return name

def apply_alias_rules(name: str, entity_type: str) -> str:
    """
    Regex/pattern-based tag normalization (e.g. P101 -> Pump P-101);
    collapse known abbreviation/acronym pairs.
    """
    # Inject hyphen between letter prefix and numeric suffix (equipment tags)
    name = re.sub(r'\b([A-Z]{1,4})(\d{1,4})\b', r'\1-\2', name)

    # Prefix mapping dictionary for tag canonicalization
    prefix_map = {
        "C": "Compressor",
        "P": "Pump",
        "R": "Reactor",
        "B": "Boiler",
        "HX": "Heat Exchanger",
        "CT": "Cooling Tower",
        "V": "Vessel"
    }

    # Check for tags like C-17, P-101, R-201, B-12, HX-34, CT-05, V-301
    tag_match = re.search(r'\b(C|P|R|B|HX|CT|V)-?(\d+)\b', name, re.IGNORECASE)
    if tag_match:
        prefix = tag_match.group(1).upper()
        num = tag_match.group(2)
        tag = f"{prefix}-{num}"
        if prefix in prefix_map:
            name = f"{prefix_map[prefix]} {tag}"
            
    return name

def resolve_entities_task(extracted_entities: List[Dict[str, Any]], tenant_id: str) -> List[Dict[str, Any]]:
    """
    Entity Resolution Pipeline
    """
    resolved = []
    
    for entity in extracted_entities:
        original_name = entity["name"]
        entity_type = entity.get("type", "Entity")
        
        normalized = normalize_entity_name(original_name)
        alias_canonical = apply_alias_rules(normalized, entity_type)
        
        # Check if we already have this exact alias mapped to something else in memory
        # Or just do vector search directly
        existing_match = find_similar_entity(
            name=alias_canonical,
            entity_type=entity_type,
            tenant_id=tenant_id
        )
        
        if existing_match:
            entity["canonical_name"] = existing_match["name"]
            entity["canonical_id"] = existing_match["canonical_id"]
            # We don't have access to existing aliases in the return payload easily, 
            # but graph_builder's MERGE handles alias array union.
            entity["aliases"] = [original_name, alias_canonical, existing_match["name"]]
            
            # Store this new alias vector so it points to canonical
            if alias_canonical != existing_match["name"]:
                store_canonical_entity_vector(alias_canonical, entity_type, existing_match["canonical_id"], tenant_id)
        else:
            entity["canonical_name"] = alias_canonical
            entity["canonical_id"] = _make_canonical_id(alias_canonical, tenant_id)
            entity["aliases"] = [original_name, alias_canonical]
            
            # Store new canonical entity vector
            store_canonical_entity_vector(alias_canonical, entity_type, entity["canonical_id"], tenant_id)
            
        # Deduplicate aliases list
        entity["aliases"] = list(set(entity["aliases"]))
        resolved.append(entity)
        
    return resolved
