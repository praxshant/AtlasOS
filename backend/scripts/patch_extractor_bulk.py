import os

file_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\ingestion\entity_extractor.py"

new_code = """
import asyncio
from dataclasses import dataclass, field

# ----- Tunables -----
CHUNKS_PER_LLM_CALL = 5
MAX_CONCURRENT_LLM = 2
LLM_TIMEOUT_S = 60

@dataclass
class ExtractionResult:
    entities: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)

def _batch_prompt(batch: list[dict]) -> str:
    parts = []
    for c in batch:
        parts.append(f"[CHUNK {c['chunk_id']}]\\n{c['text']}\\n")
    body = "\\n".join(parts)
    
    return f\"\"\"Analyze each numbered industrial text chunk and extract entities and relationships.

Use hyphen notation for equipment tags (C-17 not C17).
Entity type must be one of: {sorted(VALID_LABELS)}
Relationship type must be one of: {sorted(VALID_RELATIONSHIPS)}

Return STRICT JSON, one object per chunk:
{{
  "results": [
    {{
      "chunk_id": <int>,
      "entities": [{{"name": "...", "type": "...", "properties": {{}}, "confidence": 0.0}}],
      "relationships": [{{"source": "...", "target": "...", "type": "...", "confidence": 0.0}}]
    }}
  ]
}}

CHUNKS:
{body}
\"\"\"

def _parse_batch_response(data: dict, batch: list[dict]) -> dict[int, ExtractionResult]:
    out: dict[int, ExtractionResult] = {c["chunk_id"]: ExtractionResult() for c in batch}
    if not isinstance(data, dict):
        return out

    for item in data.get("results", []):
        cid = item.get("chunk_id")
        if cid not in out:
            continue
        ents = []
        for e in item.get("entities", []):
            etype = e.get("type")
            if etype not in VALID_LABELS:
                continue
            e["name"] = canonicalize_entity_name(e.get("name", ""))
            e.setdefault("extraction_method", "llm")
            ents.append(e)
        rels = [
            r for r in item.get("relationships", [])
            if r.get("type") in VALID_RELATIONSHIPS
        ]
        for r in rels:
            r["source"] = canonicalize_entity_name(r.get("source", ""))
            r["target"] = canonicalize_entity_name(r.get("target", ""))
        out[cid] = ExtractionResult(entities=ents, relationships=rels)
    return out

async def _call_llm(prompt: str) -> dict:
    from backend.utils.llm_client import structured_complete
    return await asyncio.to_thread(
        structured_complete,
        prompt,
        "You are a senior process safety analyst. Return strict JSON only.",
        3000
    )

async def extract_entities_batched(chunks: list[str]) -> list[ExtractionResult]:
    indexed = [{"chunk_id": i, "text": t} for i, t in enumerate(chunks)]
    batches = [
        indexed[i:i + CHUNKS_PER_LLM_CALL]
        for i in range(0, len(indexed), CHUNKS_PER_LLM_CALL)
    ]

    sem = asyncio.Semaphore(MAX_CONCURRENT_LLM)

    async def run_batch(batch: list[dict]) -> dict[int, ExtractionResult]:
        async with sem:
            try:
                raw_dict = await _call_llm(_batch_prompt(batch))
                return _parse_batch_response(raw_dict, batch)
            except Exception as e:
                logger.error("Batch extraction failed (%d chunks): %s", len(batch), e)
                return {c["chunk_id"]: ExtractionResult() for c in batch}

    batch_results = await asyncio.gather(*[run_batch(b) for b in batches])

    merged: dict[int, ExtractionResult] = {}
    for d in batch_results:
        merged.update(d)

    results: list[ExtractionResult] = []
    for i, text in enumerate(chunks):
        res = merged.get(i, ExtractionResult())
        names = {e["name"] for e in res.entities}
        for e in regex_extract_industrial_entities(text):
            if e["name"] not in names:
                res.entities.append(e)
        results.append(res)
    return results
"""

with open(file_path, "a", encoding="utf-8") as f:
    f.write("\n\n" + new_code)

print("Patched entity_extractor.py")
