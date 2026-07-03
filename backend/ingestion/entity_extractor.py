import re
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.db.postgres import Entity
from backend.utils.llm_client import structured_complete

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# VALID LABELS  — keep in sync with graph_builder VALID_RELATIONSHIPS
# ─────────────────────────────────────────────────────────────────────────────
VALID_LABELS = {
    "Asset", "Incident", "Person", "Procedure", "Regulation",
    "FailureMode", "Equipment", "LessonLearned", "AuditFinding",
    "WorkOrder", "Document", "Component", "Metric", "Organization",
    "MissingCategory",
}

# ─────────────────────────────────────────────────────────────────────────────
# VALID RELATIONSHIP TYPES
# ─────────────────────────────────────────────────────────────────────────────
VALID_RELATIONSHIPS = {
    # Core operational
    "OCCURRED_ON", "MAINTAINED_BY", "REPORTED_BY", "CAUSED_BY",
    "PREVENTS", "VIOLATES", "COMPLIES_WITH", "RELATED_TO",
    "RESULTED_IN", "APPLIES_TO", "LEARNED_FROM",
    # Graph ontology (Engineering Bible standard)
    "FOLLOWS",          # Asset follows a Procedure
    "GOVERNED_BY",      # Asset governed by Regulation
    "AFFECTED_BY",      # Asset affected by an Incident
    "DOCUMENTED_IN",    # Entity documented in a Document/Procedure
    "AUTHORED_BY",      # Procedure or document authored by a Person
    "INSPECTED_BY",     # Asset inspected by a Person
    "INVOLVED_IN",      # Person/Asset involved in an Incident
    "HAS_PROCEDURE",    # Asset has a Procedure
    "OPERATED_BY",      # Asset operated by a Person
    "PERFORMED_ON",     # WorkOrder performed on Asset
    "RESPONSE_TO",      # WorkOrder is response to Incident
    "FEEDS",            # Equipment feeds Equipment
    "SUPPLIES",         # Equipment supplies Equipment
    "BELONGS_TO",       # Component belongs to Asset
    "REFERENCES",       # Document references Procedure/Asset
    "KNOWLEDGE_OWNER",  # Person is knowledge owner of Asset
    "HAS_KNOWLEDGE_GAP", # Entity has knowledge gap
    "DOCUMENTED_BY",    # Asset documented by Document
}

# Mapping for invalid relationship types → nearest valid type
RELATIONSHIP_TYPE_MAP = {
    "AFFECTS":                "AFFECTED_BY",
    "AFFECT":                 "AFFECTED_BY",
    "REQUIRES_INPUT_FROM":    "RELATED_TO",
    "ASSOCIATED_WITH":        "RELATED_TO",
    "CONNECTED_TO":           "RELATED_TO",
    "LINKED_TO":              "RELATED_TO",
    "PART_OF":                "BELONGS_TO",
    "OWNED_BY":               "KNOWLEDGE_OWNER",
    "DOCUMENTED_BY_PERSON":   "AUTHORED_BY",
    "WRITTEN_BY":             "AUTHORED_BY",
    "DESCRIBES":              "DOCUMENTED_IN",
    "COVERS":                 "DOCUMENTED_IN",
    "IMPACTS":                "AFFECTED_BY",
    "USES":                   "FOLLOWS",
    "APPLIED_TO":             "APPLIES_TO",
    "WORKS_ON":               "PERFORMED_ON",
    "SUBMITTED_BY":           "REPORTED_BY",
}

# Equipment tag regex: P-101, R201, C-17, B-12, HX-34, V-301, etc.
EQUIPMENT_TAG_PATTERN = re.compile(
    r'\b([A-Z]{1,4})-?(\d{1,4})\b'
)

# Work Order regex: WO-8834, WO8840
WORK_ORDER_PATTERN = re.compile(
    r'\bWO-?(\d{3,6})\b', re.IGNORECASE
)

# Person-role patterns  
PERSON_ROLE_PATTERNS = re.compile(
    r'(Prepared By|Approved By|Reviewed By|Author|Inspector|Operator|Technician|'
    r'Shift Supervisor|Maintenance Engineer|Vendor|OEM|Service Engineer|Safety Officer|'
    r'Reported By|Engineer|Manager)\s*[:\-]\s*([A-Z][a-z]+ [A-Z][a-z]+)',
    re.IGNORECASE
)


def canonicalize_entity_name(name: str) -> str:
    """
    Normalises entity names so that C17, C-17, Compressor C17 all resolve
    to a single canonical ID.

    Rules applied in order:
    1. Strip leading/trailing whitespace
    2. Inject hyphen between letter prefix and number suffix:
       P101 → P-101, C17 → C-17, R201 → R-201
    3. Map known prefixes to their canonical descriptions (e.g. Compressor C-17)
    4. Collapse multiple spaces.
    """
    name = name.strip()
    # Inject hyphen between letter prefix and numeric suffix
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

    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    return name


def regex_extract_industrial_entities(text: str) -> List[dict]:
    """
    Use re module to extract common industrial entity patterns.
    These patterns are deterministic — no LLM needed.
    """
    entities = []
    seen = set()

    # 1. Equipment IDs
    for m in re.finditer(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', text):
        match_str = m.group(1)
        if match_str not in seen:
            seen.add(match_str)
            entities.append({
                "name": match_str,
                "type": "Equipment",
                "source": "regex",
                "aliases": [match_str],
                "confidence": 0.85
            })

    # 2. Work Orders
    for m in re.finditer(r'\b(WO-\d{4,6})\b', text):
        match_str = m.group(1)
        if match_str not in seen:
            seen.add(match_str)
            entities.append({
                "name": match_str,
                "type": "Incident",
                "source": "regex",
                "aliases": [match_str],
                "confidence": 0.85
            })

    # 3. Document refs
    for m in re.finditer(r'\b(SOP-\d+|ITP-\d+|SDS-\d+)\b', text):
        match_str = m.group(1)
        if match_str not in seen:
            seen.add(match_str)
            entities.append({
                "name": match_str,
                "type": "Procedure",
                "source": "regex",
                "aliases": [match_str],
                "confidence": 0.85
            })

    # 4. Regulation refs
    for m in re.finditer(r'\b(ISO\s+\d+[\d\-]*|OSHA\s+\d+|API\s+\d+|NFPA\s+\d+)\b', text):
        match_str = m.group(1).strip()
        if match_str not in seen:
            seen.add(match_str)
            entities.append({
                "name": match_str,
                "type": "Regulation",
                "source": "regex",
                "aliases": [match_str],
                "confidence": 0.85
            })
            
    return entities

def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2): return _levenshtein(s2, s1)
    if len(s2) == 0: return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def merge_and_canonicalize(regex_entities: List[dict], llm_entities: List[dict]) -> List[dict]:
    # Normalize llm entities
    for e in llm_entities:
        e["name"] = canonicalize_entity_name(e["name"])
        e["aliases"] = e.get("aliases", [e["name"]])
        e["source"] = "llm"
        e["confidence"] = e.get("confidence", 0.5)
        
    all_entities = regex_entities + llm_entities
    merged = []
    
    for entity in all_entities:
        match_found = False
        entity_name_lower = entity["name"].lower()
        eq_match = re.search(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', entity["name"])
        eq_id = eq_match.group(1).lower() if eq_match else None
        
        for m in merged:
            m_name_lower = m["name"].lower()
            m_eq_match = re.search(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', m["name"])
            m_eq_id = m_eq_match.group(1).lower() if m_eq_match else None
            
            if (entity_name_lower in m_name_lower or m_name_lower in entity_name_lower) or \
               (_levenshtein(entity_name_lower, m_name_lower) < 3) or \
               (eq_id and m_eq_id and eq_id == m_eq_id):
                match_found = True
                
                if len(entity["name"]) > len(m["name"]):
                    m["name"] = entity["name"]
                
                m["aliases"] = list(set(m.get("aliases", []) + entity.get("aliases", [])))
                
                if m["source"] == "regex" and entity["source"] == "llm":
                    m["type"] = entity.get("type", m["type"])
                    
                m["confidence"] = max(m.get("confidence", 0.5), entity.get("confidence", 0.5))
                
                if m["source"] != entity["source"]:
                    m["source"] = "regex+llm"
                break
                
        if not match_found:
            merged.append(entity)
            
    seen = set()
    final_merged = []
    for m in merged:
        cname = canonicalize_entity_name(m["name"])
        m["name"] = cname
        if cname not in seen:
            seen.add(cname)
            final_merged.append(m)
            
    return final_merged

def extract_relationships_hybrid(text: str, entities: List[dict], llm_rels: List[dict]) -> List[dict]:
    rule_rels = []
    
    for m in re.finditer(r'(WO-\d+)[^\n]*?(performed on|rebuild of|maintenance on|repair of)[^\n]*?([A-Z]{1,3}-\d{2,4})', text, re.IGNORECASE):
        rule_rels.append({
            "source": m.group(1).upper(),
            "target": m.group(3).upper(),
            "type": "PERFORMED_ON",
            "confidence": 0.80,
            "extraction_method": "rule"
        })
        
    for m in re.finditer(r'([A-Z]{1,3}-\d{2,4})\s+(feeds?|supplies?|connects? to)\s+([A-Z]{1,3}-\d{2,4})', text, re.IGNORECASE):
        rule_rels.append({
            "source": m.group(1).upper(),
            "target": m.group(3).upper(),
            "type": "FEEDS",
            "confidence": 0.80,
            "extraction_method": "rule"
        })
        
    for m in re.finditer(r'(awaiting input from|owned by|maintained by|assigned to)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', text):
        person = m.group(2)
        context_before = text[:m.start()]
        eq_matches = list(re.finditer(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', context_before))
        if eq_matches:
            closest_eq = eq_matches[-1].group(1)
            rule_rels.append({
                "source": person,
                "target": closest_eq,
                "type": "KNOWLEDGE_OWNER",
                "confidence": 0.80,
                "extraction_method": "rule"
            })
            
    for m in re.finditer(r'(SOP-\d+|Vendor Manual|PM Manual)[^\n]*?([A-Z]{1,3}-\d{2,4})', text, re.IGNORECASE):
        rule_rels.append({
            "source": m.group(1).upper(),
            "target": m.group(2).upper(),
            "type": "REFERENCES",
            "confidence": 0.80,
            "extraction_method": "rule"
        })
        
    for m in re.finditer(r'(failure|incident|catastrophic|rupture|leak|emergency)[^\n]*?([A-Z]{1,3}-\d{2,4})', text, re.IGNORECASE):
        incident_name = m.group(1).capitalize() + " Event"
        rule_rels.append({
            "source": m.group(2).upper(),
            "target": incident_name,
            "type": "AFFECTED_BY",
            "confidence": 0.80,
            "extraction_method": "rule"
        })
        
    for r in llm_rels:
        r["extraction_method"] = "llm"
        r["confidence"] = r.get("confidence", 0.5)
        
    all_rels = rule_rels + llm_rels
    
    merged = {}
    for r in all_rels:
        s = canonicalize_entity_name(r["source"])
        t = canonicalize_entity_name(r["target"])
        r_type = remap_relationship_type(r["type"])
        key = (s, t, r_type)
        if key not in merged:
            merged[key] = {
                "source": s,
                "target": t,
                "type": r_type,
                "confidence": r["confidence"],
                "extraction_method": r["extraction_method"]
            }
        else:
            merged[key]["confidence"] = max(merged[key]["confidence"], r["confidence"])
            if merged[key]["extraction_method"] != r["extraction_method"]:
                merged[key]["extraction_method"] = "rule+llm"
                
    return list(merged.values())

def score_entity_confidence(entities: List[dict]) -> List[dict]:
    scored = []
    for e in entities:
        base = 0.5
        source = e.get("source", "llm")
        if source == "regex+llm":
            base += 0.20
        elif source == "regex":
            base += 0.15
            
        if len(e.get("aliases", [])) > 1:
            base += 0.10
            
        if len(e["name"]) < 3:
            base -= 0.15
            
        if e.get("confidence", 1.0) < 0.4:
            base -= 0.10
            
        e["confidence"] = min(1.0, max(0.0, base))
        if e["confidence"] >= 0.35:
            scored.append(e)
    return scored

def score_relationship_confidence(relationships: List[dict]) -> List[dict]:
    STRONG_TYPES = {"CAUSED_BY", "PERFORMED_ON", "PREVENTS", "COMPLIES_WITH"}
    scored = []
    for r in relationships:
        base = 0.5
        method = r.get("extraction_method", "llm")
        if method == "rule+llm":
            base += 0.30
        elif method == "rule":
            base += 0.20
        elif method == "llm" and r["type"] in STRONG_TYPES:
            base += 0.10
            
        r["confidence"] = min(1.0, max(0.0, base))
        scored.append(r)
    return scored


def remap_relationship_type(rel_type: str) -> str:
    """Maps invalid/unusual relationship types to the nearest valid type."""
    if rel_type in VALID_RELATIONSHIPS:
        return rel_type
    return RELATIONSHIP_TYPE_MAP.get(rel_type, "RELATED_TO")


def build_extraction_prompt(chunk_text: str) -> str:
    """
    Builds the LLM system/user prompt for entity & relation extraction.
    """
    prompt = f"""Analyze the following industrial operations text and extract ALL entities and relationships.

Text:
---
{chunk_text}
---

ENTITY EXTRACTION RULES:
1. Extract every meaningful entity. Each entity must have:
   - name: Canonical name with hyphen notation (e.g. "Pump P-101", "C-17", "WO-8834", "Rahul Mehta")
   - type: EXACTLY one of: {sorted(list(VALID_LABELS))}
   - properties: Key-value dict (location, code, severity, date, department, description, role)
   - confidence: float 0.0–1.0

2. PERSON DETECTION: Extract named people appearing after any of:
   Prepared By, Approved By, Inspector, Operator, Technician, Shift Supervisor,
   Maintenance Engineer, Vendor, OEM, Reported By, Authored By, Engineer, Reviewed By.

3. EQUIPMENT DETECTION: Extract all equipment tags (P-101, R-201, C-17, V-301, B-12, HX-34,
   K-201 etc.) as Equipment entities. Keep hyphen notation. (Pump P-101, Compressor C-17).

4. WORK ORDER DETECTION: Extract WO-XXXX patterns as WorkOrder entities.

5. DOCUMENT DETECTION: SOPs, Manuals, Reports, Procedures, Forms → type=Document.

6. INCIDENT DETECTION: Failures, shutdowns, alarms, trips, outages → type=Incident.

RELATIONSHIP EXTRACTION RULES:
Extract all direct relationships. Each must have:
- source, target, type (EXACTLY one of: {sorted(list(VALID_RELATIONSHIPS))}), confidence 0.0-1.0

Use specific types: CAUSED_BY, RESULTED_IN, PERFORMED_ON, AUTHORED_BY, AFFECTED_BY,
FOLLOWS, GOVERNED_BY, DOCUMENTED_IN, HAS_PROCEDURE, OPERATED_BY, INSPECTED_BY.

Return ONLY valid JSON (no markdown, no extra text):
{{
  "entities": [
    {{ "name": "C-17", "type": "Equipment", "properties": {{ "description": "Rotary screw compressor" }}, "confidence": 0.95 }}
  ],
  "relationships": [
    {{ "source": "C-17", "target": "Bearing Failure 2025", "type": "AFFECTED_BY", "confidence": 0.90 }}
  ]
}}"""
    return prompt


def extract_entities_and_relationships(chunk_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Combines deterministic rules + LLM extraction.
    Returns (entities, relationships).
    """
    if not chunk_text.strip():
        return [], []

    # Step 1: Regex pre-extraction
    regex_candidates = regex_extract_industrial_entities(chunk_text)

    # Step 2: LLM extraction
    prompt = build_extraction_prompt(chunk_text)
    system_prompt = (
        "You are a senior process safety and industrial operations analyst. "
        "Extract entities and relationships from the provided industrial text in strict JSON format. "
        "Be thorough — missing entities is worse than including borderline ones. "
        "Always use hyphen notation for equipment tags (C-17 not C17)."
    )

    try:
        data = structured_complete(prompt, system_prompt=system_prompt, max_tokens=3000)
        llm_entities = data.get("entities", [])
        llm_relationships = data.get("relationships", [])
    except Exception as e:
        logger.error(f"LLM extraction failed for chunk: {e}")
        llm_entities = []
        llm_relationships = []

    # Filter LLM entities to valid labels
    valid_llm_entities = [e for e in llm_entities if e.get("type") in VALID_LABELS and e.get("name")]

    # Step 3: Merge and deduplicate
    merged_entities = merge_and_canonicalize(regex_candidates, valid_llm_entities)

    # Step 4: Extract relationships (hybrid)
    relationships = extract_relationships_hybrid(chunk_text, merged_entities, llm_relationships)

    # Step 5: Score confidence
    scored_entities = score_entity_confidence(merged_entities)
    
    canonical_names = {e["name"] for e in scored_entities}
    valid_relationships = [r for r in relationships if r["source"] in canonical_names and r["target"] in canonical_names]
    
    scored_relationships = score_relationship_confidence(valid_relationships)

    return scored_entities, scored_relationships


def deduplicate_and_save_entities(db: Session, entities: List[Dict[str, Any]], doc_id: int, tenant_id: str) -> Dict[Tuple[str, str], int]:
    """
    Canonicalises, deduplicates, and saves entities to PostgreSQL.
    Returns a mapping of (canonical_name, entity_type) -> postgres_entity_id.
    """
    entity_mapping = {}

    for entity_data in entities:
        name = canonicalize_entity_name(entity_data["name"].strip())
        etype = entity_data.get("type", "Equipment")
        if etype not in VALID_LABELS:
            etype = "Equipment"
        confidence = entity_data.get("confidence", 1.0)

        # Case-insensitive deduplication
        existing_entity = db.query(Entity).filter(
            Entity.tenant_id == tenant_id,
            Entity.canonical_name.ilike(name),
            Entity.entity_type == etype
        ).first()

        if existing_entity:
            entity_mapping[(name.lower(), etype)] = existing_entity.id
        else:
            new_entity = Entity(
                tenant_id=tenant_id,
                canonical_name=name,
                entity_type=etype,
                confidence=confidence,
                source_doc_id=doc_id
            )
            db.add(new_entity)
            db.flush()
            entity_mapping[(name.lower(), etype)] = new_entity.id

    return entity_mapping


def batch_extract_entities(texts: List[str], tenant_id: str = None) -> List[Dict[str, Any]]:
    """
    Extracts entities and relationships for a list of texts using parallel processing.
    Uses ThreadPoolExecutor to run LLM calls concurrently (up to 4 workers).
    """
    if not texts:
        return []

    results = [None] * len(texts)
    max_workers = min(4, len(texts))

    def _extract(idx: int, text: str) -> Tuple[int, Dict[str, Any]]:
        entities, relationships = extract_entities_and_relationships(text)
        return idx, {"entities": entities, "relationships": relationships}

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_extract, i, text): i for i, text in enumerate(texts)}
            for future in as_completed(futures):
                try:
                    idx, result = future.result(timeout=90)
                    results[idx] = result
                    logger.info(
                        f"[EntityExtractor] Chunk {idx}: extracted "
                        f"{len(result['entities'])} entities, "
                        f"{len(result['relationships'])} relationships"
                    )
                except Exception as e:
                    original_idx = futures[future]
                    logger.warning(f"[EntityExtractor] Chunk {original_idx} failed: {e}. Inserting empty result.")
                    results[original_idx] = {"entities": [], "relationships": []}
    except Exception as e:
        logger.warning(f"[EntityExtractor] Parallel extraction failed ({e}), falling back to serial.")
        results = []
        for text in texts:
            entities, relationships = extract_entities_and_relationships(text)
            results.append({"entities": entities, "relationships": relationships})

    return [r if r is not None else {"entities": [], "relationships": []} for r in results]
