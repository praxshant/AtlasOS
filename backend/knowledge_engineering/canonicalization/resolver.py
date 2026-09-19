import logging
import uuid
from typing import Dict, Any, Optional
from backend.vector.qdrant_client import qdrant_client
import re

logger = logging.getLogger(__name__)

# Constants
ENTITY_COLLECTION = "entities"
SIMILARITY_THRESHOLD = 0.93

def _init_entity_collection():
    qdrant_client.ensure_collection(ENTITY_COLLECTION)

def _make_canonical_id(n: str, tenant_id: str = "default") -> str:
    normalized = n.strip().upper().replace(" ", "_")
    normalized = re.sub(r'[^A-Z0-9_]', '', normalized)
    return f"{tenant_id}:{normalized}"

def find_similar_entity(name: str, entity_type: str, tenant_id: str, similarity_threshold: float = SIMILARITY_THRESHOLD) -> Optional[Dict[str, Any]]:
    """
    Searches Qdrant `entities` collection for high-similarity matches.
    Returns the payload of the best match if found, else None.
    """
    try:
        qdrant_client._load_embed_model()
        if not qdrant_client._embed_model:
            return None
            
        vector = qdrant_client._embed_model.encode(name).tolist()
        
        client = qdrant_client.get_client()
        if not client:
            return None
            
        _init_entity_collection()
        
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        
        must_conditions = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        if entity_type:
            must_conditions.append(FieldCondition(key="type", match=MatchValue(value=entity_type)))
            
        results = client.query_points(
            collection_name=ENTITY_COLLECTION,
            query=vector,
            query_filter=Filter(must=must_conditions),
            limit=1,
            score_threshold=similarity_threshold
        ).points
        
        if results:
            match = results[0]
            logger.info(f"Canonicalization: Merged '{name}' into existing '{match.payload.get('name')}' (Score: {match.score:.3f})")
            return match.payload
            
        return None
        
    except Exception as e:
        logger.error(f"Error resolving entity '{name}': {e}")
        return None

def store_canonical_entity_vector(name: str, entity_type: str, canonical_id: str, tenant_id: str):
    """Stores the vector for a specific alias so it points to the canonical_id"""
    try:
        qdrant_client._load_embed_model()
        if not qdrant_client._embed_model:
            return
            
        vector = qdrant_client._embed_model.encode(name).tolist()
        
        client = qdrant_client.get_client()
        if not client:
            return
            
        _init_entity_collection()
        
        from qdrant_client.http.models import PointStruct
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tenant_id}_{canonical_id}_{name}"))
        
        client.upsert(
            collection_name=ENTITY_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "name": name,
                        "type": entity_type,
                        "canonical_id": canonical_id,
                        "tenant_id": tenant_id
                    }
                )
            ]
        )
    except Exception as e:
        logger.warning(f"Failed to store alias vector for {name}: {e}")
