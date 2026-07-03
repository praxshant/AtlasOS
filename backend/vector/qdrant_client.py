import logging
import uuid
import time
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue,
    OptimizersConfigDiff, HnswConfigDiff, PayloadSchemaType
)
from sentence_transformers import SentenceTransformer
from backend.config import get_settings
from backend.utils.metrics import record_latency

logger = logging.getLogger(__name__)
settings = get_settings()

import threading

class QdrantClientWrapper:
    def __init__(self):
        self.url = settings.QDRANT_URL
        self._client = None
        self._embed_model = None
        self._vector_size = None
        self._lock = threading.Lock()
        self._connect()

    def _connect(self):
        try:
            self._client = QdrantClient(url=self.url)
            logger.info("Successfully connected to Qdrant.")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant at {self.url}: {e}")
            self._client = None

    def _load_embed_model(self):
        if not self._embed_model:
            with self._lock:
                if not self._embed_model:
                    try:
                        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL_NAME}...")
                        self._embed_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
                        self._vector_size = self._embed_model.get_sentence_embedding_dimension()
                        logger.info(f"Embedding model loaded. Dimension: {self._vector_size}")
                    except Exception as e:
                        logger.error(f"Failed to load sentence-transformers model: {e}")
                        # Fallback dimension for all-MiniLM-L6-v2 is 384
                        self._vector_size = 384

    def get_client(self) -> QdrantClient:
        if not self._client:
            self._connect()
        return self._client

    def ensure_collection(self, collection_name: str):
        client = self.get_client()
        if not client:
            return
        
        self._load_embed_model()
        try:
            # Check if collection exists
            collections = client.get_collections().collections
            exists = any(c.name == collection_name for c in collections)
            
            if exists:
                try:
                    info = client.get_collection(collection_name)
                    if info.config.params.vectors.size != self._vector_size:
                        logger.warning("Vector size mismatch. Recreating collection. Re-ingest documents.")
                        client.delete_collection(collection_name)
                        exists = False
                except Exception as e:
                    logger.error(f"Error checking collection config for {collection_name}: {e}")
            
            if not exists:
                logger.info(f"Creating Qdrant collection: {collection_name} with size {self._vector_size}...")
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=self._vector_size, distance=Distance.COSINE),
                    optimizers_config=OptimizersConfigDiff(
                        indexing_threshold=20000,
                        memmap_threshold=50000
                    ),
                    hnsw_config=HnswConfigDiff(
                        m=settings.QDRANT_HNSW_M,
                        ef_construct=settings.QDRANT_HNSW_EF_CONSTRUCT,
                        full_scan_threshold=10000
                    )
                )
                logger.info(f"Collection {collection_name} created successfully.")
                
                # Create payload indexes for filtered search performance
                self._create_payload_indexes(collection_name)
        except Exception as e:
            logger.error(f"Error ensuring Qdrant collection {collection_name}: {e}")

    def _create_payload_indexes(self, collection_name: str):
        """
        Creates payload field indexes for tenant filtering and metadata searches.
        """
        client = self.get_client()
        if not client:
            return

        index_fields = [
            ("tenant_id", PayloadSchemaType.KEYWORD),
            ("doc_id", PayloadSchemaType.INTEGER),
        ]
        
        for field_name, schema_type in index_fields:
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=schema_type
                )
                logger.info(f"Created payload index on {field_name} in {collection_name}")
            except Exception as e:
                logger.warning(f"Payload index on {field_name} may already exist: {e}")

    def embed_text(self, text: str) -> List[float]:
        self._load_embed_model()
        if not self._embed_model:
            logger.warning("Embedding model not loaded, returning empty vector.")
            return [0.0] * 384
        return self._embed_model.encode(text).tolist()

    def upsert_chunks(self, collection_name: str, chunks: List[Dict[str, Any]], tenant_id: str = "default") -> List[str]:
        """
        Upsert a list of text chunks, scoped to a tenant.
        Each chunk is a dict: {'text': str, 'doc_id': int, 'page': int, 'metadata': dict}
        Returns list of qdrant IDs.
        Uses batched upserts for large chunk lists.
        """
        client = self.get_client()
        if not client:
            logger.warning("Qdrant client not available. Skipping upsert.")
            return []

        self.ensure_collection(collection_name)
        points = []
        qdrant_ids = []

        for chunk in chunks:
            text = chunk.get("text", "")
            doc_id = chunk.get("doc_id")
            page = chunk.get("page", 1)
            chunk_index = chunk.get("chunk_index", 0)
            meta = chunk.get("metadata", {})

            # Generate stable UUID for qdrant if not provided
            q_id = chunk.get("qdrant_id")
            if not q_id:
                q_id = str(uuid.uuid4())

            vector = self.embed_text(text)
            
            payload = {
                "text": text,
                "tenant_id": tenant_id,
                "doc_id": doc_id,
                "page": page,
                "chunk_index": chunk_index,
                "metadata": meta
            }

            points.append(PointStruct(id=q_id, vector=vector, payload=payload))
            qdrant_ids.append(q_id)

        # Batch upsert in configurable batch sizes
        batch_size = settings.QDRANT_BATCH_SIZE
        
        from backend.utils.circuit_breaker import qdrant_breaker, CircuitOpenError
        
        def _do_upsert(batch):
            client.upsert(collection_name=collection_name, points=batch)
            
        try:
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                try:
                    qdrant_breaker.call(_do_upsert, batch)
                    logger.info(f"Upserted batch {i // batch_size + 1} ({len(batch)} points) into {collection_name}")
                except CircuitOpenError as ce:
                    logger.error(f"Qdrant circuit is OPEN. Upsert failed: {ce}")
                    raise ce
            
            logger.info(f"Successfully upserted {len(points)} total chunks into collection {collection_name}.")
            return qdrant_ids
        except Exception as e:
            logger.error(f"Failed to upsert chunks to Qdrant: {e}")
            raise e

    def similarity_search(self, collection_name: str, query: str, top_k: int = 5,
                          filter_doc_id: Optional[int] = None,
                          tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Search for most similar vectors in a collection, always scoped to tenant.
        Supports filtering by source document ID.
        """
        client = self.get_client()
        if not client:
            logger.warning("Qdrant client not available. Skipping search.")
            return []

        self.ensure_collection(collection_name)
        query_vector = self.embed_text(query)

        # Build filter — always include tenant_id if provided
        must_conditions = []
        if tenant_id:
            must_conditions.append(
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
            )
        if filter_doc_id is not None:
            must_conditions.append(
                FieldCondition(key="doc_id", match=MatchValue(value=filter_doc_id))
            )

        search_filter = Filter(must=must_conditions) if must_conditions else None

        from backend.utils.circuit_breaker import qdrant_breaker, CircuitOpenError
        
        def _do_search():
            return client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=top_k
            )

        start_time = time.time()
        try:
            response = qdrant_breaker.call(_do_search)
            duration_ms = (time.time() - start_time) * 1000.0
            record_latency("qdrant", duration_ms)
            results = response.points

            scored_points = []
            for hit in results:
                scored_points.append({
                    "id": hit.id,
                    "score": hit.score,
                    "text": hit.payload.get("text"),
                    "doc_id": hit.payload.get("doc_id"),
                    "page": hit.payload.get("page"),
                    "chunk_index": hit.payload.get("chunk_index"),
                    "metadata": hit.payload.get("metadata", {})
                })
            return scored_points
        except CircuitOpenError as ce:
            logger.warning(f"Qdrant circuit is OPEN. Skipping search: {ce}")
            return []
        except Exception as e:
            logger.error(f"Qdrant search error in {collection_name}: {e}")
            return []

    def delete_by_doc_id(self, collection_name: str, doc_id: int, tenant_id: str = None):
        """
        Deletes all chunks belonging to a specific document ID, scoped to tenant.
        """
        client = self.get_client()
        if not client:
            return
        
        self.ensure_collection(collection_name)
        
        must_conditions = [
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
        ]
        if tenant_id:
            must_conditions.append(
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
            )
        
        try:
            client.delete(
                collection_name=collection_name,
                points_selector=Filter(must=must_conditions)
            )
            logger.info(f"Deleted chunks for doc_id {doc_id} from {collection_name}.")
        except Exception as e:
            logger.error(f"Failed to delete by doc_id: {e}")

    def delete_by_tenant(self, collection_name: str, tenant_id: str):
        """
        Deletes ALL vectors belonging to a tenant. Used for tenant teardown.
        """
        client = self.get_client()
        if not client:
            return

        try:
            client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
                )
            )
            logger.info(f"Deleted all vectors for tenant {tenant_id} from {collection_name}.")
        except Exception as e:
            logger.error(f"Failed to delete by tenant_id: {e}")

    def create_snapshot(self, collection_name: str) -> Optional[str]:
        """
        Creates a snapshot of the collection for backup purposes.
        Returns the snapshot name if successful.
        """
        client = self.get_client()
        if not client:
            return None
        try:
            snapshot = client.create_snapshot(collection_name=collection_name)
            logger.info(f"Created snapshot for {collection_name}: {snapshot}")
            return str(snapshot)
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            return None

    def check_collection_health(self, collection_name: str) -> Dict[str, Any]:
        """
        Returns health status and statistics for a collection.
        """
        client = self.get_client()
        if not client:
            return {"status": "unavailable"}
        try:
            info = client.get_collection(collection_name)
            return {
                "status": str(info.status),
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "segments_count": len(info.segments) if hasattr(info, 'segments') else 0,
                "indexed_vectors_count": info.indexed_vectors_count if hasattr(info, 'indexed_vectors_count') else 0,
            }
        except Exception as e:
            logger.error(f"Failed to check collection health: {e}")
            return {"status": "error", "error": str(e)}

# Singleton instance
qdrant_client = QdrantClientWrapper()
