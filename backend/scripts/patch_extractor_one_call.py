import os
import re

# 1. Patch entity_extractor.py
extractor_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\ingestion\entity_extractor.py"
with open(extractor_path, "r", encoding="utf-8") as f:
    extractor_content = f.read()

extractor_new_methods = """
import hashlib
from backend.db.postgres import SessionLocal, CachedExtraction
from backend.config import get_settings

def _get_doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def extract_entities_one_call(full_document_text: str, tenant_id: str, doc_id: int) -> dict:
    \"\"\"
    One LLM call per document + Regex + Cache.
    Returns: {"entities": [...], "relationships": [...]}
    \"\"\"
    settings = get_settings()
    doc_hash = _get_doc_hash(full_document_text)
    
    db = SessionLocal()
    try:
        # 1. Check Cache
        cached = db.query(CachedExtraction).filter(CachedExtraction.file_hash == doc_hash).first()
        if cached:
            try:
                logger.info(f"Using cached extraction for doc_id {doc_id}")
                return json.loads(cached.llm_json)
            except Exception as e:
                logger.warning(f"Failed to load cached extraction: {e}")
        
        # 2. Regex Extraction
        regex_entities, regex_rels = regex_extract_industrial_entities(full_document_text)
        
        # 3. LLM Extraction (Optional if disabled)
        llm_entities, llm_rels = [], []
        if not settings.DISABLE_LLM_EXTRACTION:
            # We skip sending the huge regex list to LLM to save tokens, we just let LLM extract what it can
            # But we could optionally scrub regex terms.
            prompt = _build_extraction_prompt(full_document_text)
            sys_prompt = "You are an expert Industrial Knowledge Graph extractor. Only output valid JSON matching the schema."
            from backend.utils.llm_provider import get_provider
            
            try:
                provider = get_provider()
                res = provider.structured_complete(prompt, system_prompt=sys_prompt, max_tokens=2500)
                if isinstance(res, dict) and "entities" in res:
                    llm_entities = res.get("entities", [])
                    llm_rels = res.get("relationships", [])
            except Exception as e:
                logger.error(f"LLM extraction failed: {e}")
                
        # 4. Merge results
        # Normalize and filter
        all_entities = regex_entities + llm_entities
        all_rels = regex_rels + llm_rels
        
        final_entities = []
        seen_entities = set()
        for e in all_entities:
            c_name = canonicalize_entity_name(e.get("name", ""))
            if not c_name: continue
            if c_name not in seen_entities:
                seen_entities.add(c_name)
                # Keep valid labels only
                lbl = e.get("type", "Entity")
                if lbl not in VALID_LABELS:
                    lbl = "Entity"
                final_entities.append({
                    "name": c_name,
                    "canonical_id": c_name,
                    "type": lbl,
                    "confidence": e.get("confidence", 1.0),
                    "tenant_id": tenant_id,
                    "document_id": doc_id
                })
                
        final_rels = []
        for r in all_rels:
            src = canonicalize_entity_name(r.get("source", ""))
            tgt = canonicalize_entity_name(r.get("target", ""))
            if not src or not tgt: continue
            
            rel_type = r.get("type", "RELATED_TO").upper().replace(" ", "_")
            if rel_type not in VALID_RELATIONSHIPS:
                rel_type = RELATIONSHIP_TYPE_MAP.get(rel_type, "RELATED_TO")
                
            final_rels.append({
                "source": src,
                "target": tgt,
                "type": rel_type,
                "confidence": r.get("confidence", 1.0),
                "tenant_id": tenant_id,
                "document_id": doc_id
            })
            
        final_result = {"entities": final_entities, "relationships": final_rels}
        
        # 5. Save to Cache
        if not settings.DISABLE_LLM_EXTRACTION: # Only cache if LLM actually ran
            try:
                cache_entry = CachedExtraction(
                    file_hash=doc_hash,
                    provider=settings.LLM_PROVIDER,
                    llm_json=json.dumps(final_result)
                )
                db.add(cache_entry)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning(f"Failed to cache extraction: {e}")
                
        return final_result
    finally:
        db.close()
"""

# Replace batch methods if they exist, else append
if "def extract_entities_one_call" not in extractor_content:
    extractor_content += "\n" + extractor_new_methods
    
    # Optional: Update regex in extractor
    regex_old = """    # Find Equipment tags"""
    regex_new = """    # Add missing markers
    if "[TBD]" in text or "[CONTENT MISSING]" in text or "[DRAFT]" in text:
        entities.append({"name": "Content Gap", "type": "MissingCategory", "confidence": 1.0})
    
    # Find Equipment tags"""
    extractor_content = extractor_content.replace(regex_old, regex_new)
    
    with open(extractor_path, "w", encoding="utf-8") as f:
        f.write(extractor_content)

# 2. Patch ingestion_tasks.py
tasks_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\tasks\ingestion_tasks.py"
with open(tasks_path, "r", encoding="utf-8") as f:
    tasks_content = f.read()
    
task_old = """        from backend.ingestion.entity_extractor import extract_entities_batched
        results = _run_async(extract_entities_batched(texts))
        
        all_entities: dict[str, dict] = {}
        all_rels: list[dict] = []
        for idx, res in enumerate(results):
            for e in res.entities:
                key = e["name"]
                if key not in all_entities:
                    e["canonical_id"] = key
                    e["tenant_id"] = prev['tenant_id']
                    e["document_id"] = doc.id
                    all_entities[key] = e
            for r in res.relationships:
                r["tenant_id"] = prev['tenant_id']
                r["document_id"] = doc.id
                all_rels.append(r)
                
        entities = list(all_entities.values())"""

task_new = """        from backend.ingestion.entity_extractor import extract_entities_one_call
        full_text = "\\n\\n".join(texts)
        result = extract_entities_one_call(full_text, tenant_id=prev['tenant_id'], doc_id=doc.id)
        
        entities = result.get("entities", [])
        all_rels = result.get("relationships", [])"""
tasks_content = tasks_content.replace(task_old, task_new)

with open(tasks_path, "w", encoding="utf-8") as f:
    f.write(tasks_content)

print("Extractor and Tasks patched")
