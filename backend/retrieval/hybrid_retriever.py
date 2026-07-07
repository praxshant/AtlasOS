import logging
import re
import numpy as np
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from backend.db.postgres import SessionLocal, Chunk, Document
from backend.vector.qdrant_client import qdrant_client
from backend.graph.neo4j_client import neo4j_client
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class HybridRetriever:
    def __init__(self):
        self._cross_encoder = None
        self._bi_encoder = None

    def _load_models(self):
        if not self._cross_encoder:
            try:
                self._cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
            except Exception as e:
                logger.error(f"Failed to load cross-encoder: {e}")
                
        if not self._bi_encoder:
            try:
                # We can reuse the Qdrant client's embedding model to save memory
                qdrant_client._load_embed_model()
                self._bi_encoder = qdrant_client._embed_model
            except Exception as e:
                logger.error(f"Failed to load bi-encoder for MMR: {e}")

    def classify_query(self, query: str) -> Dict[str, Any]:
        """Retrieval 3.0 Intent Detection & Adaptive Parameters"""
        q = query.lower()
        query_type = "general"
        if any(w in q for w in ["pump", "reactor", "compressor", "valve", "asset", "equipment"]):
            query_type = "asset"
        elif any(w in q for w in ["failure", "incident", "accident", "fault", "broke", "failed"]):
            query_type = "incident"
        elif any(w in q for w in ["sop", "procedure", "how to", "steps", "protocol"]):
            query_type = "procedure"
        elif any(w in q for w in ["regulation", "compliance", "iso", "osha", "requirement"]):
            query_type = "compliance"
        elif any(w in q for w in ["engineer", "who knows", "expert", "person", "staff"]):
            query_type = "engineer"
        elif any(w in q for w in ["gap", "missing", "risk", "coverage", "unknown"]):
            query_type = "risk"
        elif any(w in q for w in ["uploaded", "document", "file", "registry", "metadata"]):
            if any(w in q for w in ["how many", "list", "what"]):
                query_type = "metadata"
            
        equipment_ids = re.findall(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', query)
        
        # Adaptive Top-K based on complexity
        word_count = len(q.split())
        is_complex = word_count > 10 or len(equipment_ids) > 1
        
        initial_k = 30 if is_complex else 20
        rerank_k = 15 if is_complex else 8
        
        return {
            "query_type": query_type,
            "equipment_ids": list(set(equipment_ids)),
            "temporal": "1y" if "last year" in q else None,
            "is_failure_query": "why" in q and "fail" in q,
            "initial_k": initial_k,
            "rerank_k": rerank_k
        }

    def bm25_retrieval(self, query: str, tenant_id: str, top_k: int = 20) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            chunks = db.query(Chunk).filter(Chunk.tenant_id == tenant_id).all()
            if not chunks:
                return []
                
            tokenized_corpus = [chunk.text_content.lower().split() for chunk in chunks]
            bm25 = BM25Okapi(tokenized_corpus)
            
            tokenized_query = query.lower().split()
            doc_scores = bm25.get_scores(tokenized_query)
            
            top_n = np.argsort(doc_scores)[::-1][:top_k]
            
            results = []
            doc_ids = list(set([chunks[idx].document_id for idx in top_n if doc_scores[idx] > 0]))
            docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
            doc_map = {d.id: d.filename for d in docs}

            for idx in top_n:
                if doc_scores[idx] > 0:
                    c = chunks[idx]
                    results.append({
                        "id": str(c.id),
                        "text": c.text_content,
                        "doc_id": c.document_id,
                        "page": c.page_number,
                        "score": float(doc_scores[idx]),
                        "source": "bm25",
                        "metadata": {"source_file": doc_map.get(c.document_id, "Document")}
                    })
            return results
        finally:
            db.close()

    def rrf_fusion(self, dense_results: List[Dict[str, Any]], sparse_results: List[Dict[str, Any]], k: int = 60) -> List[Dict[str, Any]]:
        rrf_scores = {}
        items = {}
        
        for rank, item in enumerate(dense_results):
            key = item.get("text", "")
            items[key] = item
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            
        for rank, item in enumerate(sparse_results):
            key = item.get("text", "")
            if key not in items:
                items[key] = item
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            
        fused = []
        for key, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            item = items[key].copy()
            item["rrf_score"] = score
            fused.append(item)
            
        return fused

    def deduplicate(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strict deduplication by content."""
        seen = set()
        deduped = []
        for c in chunks:
            text = c.get("text", "").strip()
            if text and text not in seen:
                seen.add(text)
                deduped.append(c)
        return deduped

    def mmr(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 15, lambda_mult: float = 0.5) -> List[Dict[str, Any]]:
        """Maximal Marginal Relevance."""
        if not chunks:
            return []
        self._load_models()
        if not self._bi_encoder:
            return chunks[:top_k]

        texts = [c["text"] for c in chunks]
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            doc_embeddings = self._bi_encoder.encode(texts)
            query_embedding = self._bi_encoder.encode([query])
            
            doc_sims = cosine_similarity(query_embedding, doc_embeddings)[0]
            doc_doc_sims = cosine_similarity(doc_embeddings, doc_embeddings)
            
            selected = []
            unselected = list(range(len(chunks)))
            
            while len(selected) < top_k and unselected:
                if not selected:
                    best_idx = unselected[np.argmax(doc_sims[unselected])]
                else:
                    max_sim_to_selected = np.max(doc_doc_sims[unselected][:, selected], axis=1)
                    mmr_scores = lambda_mult * doc_sims[unselected] - (1 - lambda_mult) * max_sim_to_selected
                    best_idx = unselected[np.argmax(mmr_scores)]
                    
                selected.append(best_idx)
                unselected.remove(best_idx)
                
            return [chunks[i] for i in selected]
        except Exception as e:
            logger.error(f"MMR failed, returning original chunks: {e}")
            return chunks[:top_k]

    def graph_expansion(self, chunks: List[Dict[str, Any]], equipment_ids: List[str], tenant_id: str) -> List[Dict[str, Any]]:
        """Extracts Graph Nodes connected to entities mentioned in the top semantic chunks."""
        # Find entities in chunks
        chunk_entities = set(equipment_ids)
        for c in chunks:
            text = c.get("text", "")
            found = re.findall(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', text)
            chunk_entities.update(found)
            
        if not chunk_entities:
            return chunks
            
        synthetic_chunks = []
        try:
            subgraph = neo4j_client.get_multihop_subgraph(list(chunk_entities)[:5], max_depth=1, limit=50, tenant_id=tenant_id)
            nodes = subgraph.get("nodes", [])
            for node in nodes:
                name = node.get("name", "Unknown")
                label = node.get("label", "Entity")
                props = {k: v for k, v in node.items() if k not in ["name", "label", "score"]}
                desc = f"Graph Node ({label}): {name}. "
                if props:
                    desc += ", ".join([f"{k}={v}" for k, v in props.items()])
                
                synthetic_chunks.append({
                    "id": f"graph_{name}",
                    "text": desc,
                    "source": "Knowledge Graph",
                    "metadata": {"source_file": "Knowledge Graph", "is_graph": True, "pagerank": props.get("pagerank", 0.0)}
                })
        except Exception as e:
            logger.error(f"Graph expansion failed: {e}")
            
        # Append graph chunks to the candidate list
        return chunks + synthetic_chunks

    def cross_encoder_rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        self._load_models()
        if not self._cross_encoder:
            return candidates[:top_k]
            
        pairs = [[query, doc["text"]] for doc in candidates]
        try:
            scores = self._cross_encoder.predict(pairs)
            for i, score in enumerate(scores):
                candidates[i]["rerank_score"] = float(score)
            
            candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
            return candidates[:top_k]
        except Exception as e:
            logger.error(f"Cross-encoder reranking failed: {e}")
            return candidates[:top_k]

    def heuristic_context_compression(self, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Removes low-relevance sentences from chunks if they are too long."""
        self._load_models()
        if not self._bi_encoder:
            return chunks
            
        compressed = []
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            query_emb = self._bi_encoder.encode([query])
            
            for chunk in chunks:
                text = chunk.get("text", "")
                if len(text.split()) < 50:
                    compressed.append(chunk)
                    continue
                    
                # Split into sentences roughly
                sentences = re.split(r'(?<=[.!?]) +', text)
                if len(sentences) < 3:
                    compressed.append(chunk)
                    continue
                    
                sent_embs = self._bi_encoder.encode(sentences)
                sims = cosine_similarity(query_emb, sent_embs)[0]
                
                # Keep sentences above threshold or top N
                threshold = 0.2
                kept = [s for idx, s in enumerate(sentences) if sims[idx] >= threshold]
                
                # Always keep at least 2 sentences
                if len(kept) < 2:
                    top_idx = np.argsort(sims)[::-1][:2]
                    kept = [sentences[i] for i in sorted(top_idx)]
                    
                new_text = " ".join(kept)
                new_chunk = chunk.copy()
                new_chunk["text"] = new_text
                compressed.append(new_chunk)
                
            return compressed
        except Exception as e:
            logger.error(f"Context compression failed: {e}")
            return chunks

    def retrieve(self, query: str, tenant_id: str, query_type: str = "general") -> List[Dict[str, Any]]:
        # 1. Intent Detection
        intent = self.classify_query(query)
        initial_k = intent["initial_k"]
        rerank_k = intent["rerank_k"]
        resolved_type = query_type if query_type != "general" else intent["query_type"]
        
        # 2. Dense Search
        dense = qdrant_client.similarity_search("document_chunks", query, top_k=initial_k, tenant_id=tenant_id)
        filtered_dense = []
        for chunk in dense:
            sec_type = chunk.get("metadata", {}).get("section_type", "general")
            if resolved_type == "incident" and sec_type not in ["work_order", "incident_report", "failure_analysis", "rca", "general"]:
                continue
            if resolved_type == "procedure" and sec_type not in ["procedure", "warning"]:
                continue
            if resolved_type == "compliance" and sec_type != "compliance":
                continue
            filtered_dense.append(chunk)

        # 3. Sparse Search (BM25)
        sparse = self.bm25_retrieval(query, tenant_id, top_k=initial_k)

        # 4. Fusion & Deduplication
        fused = self.rrf_fusion(filtered_dense, sparse)
        deduped = self.deduplicate(fused)
        
        # 5. MMR (Diversity)
        diverse_chunks = self.mmr(query, deduped, top_k=initial_k, lambda_mult=0.6)
        
        # 6. Graph Neighborhood Expansion
        expanded = self.graph_expansion(diverse_chunks, intent["equipment_ids"], tenant_id)
        
        # 7. Cross-Encoder Reranking
        reranked = self.cross_encoder_rerank(query, expanded, top_k=rerank_k)
        
        # 8. Context Compression
        compressed = self.heuristic_context_compression(query, reranked)
        
        # Ensure 'source' is in metadata for citations
        for item in compressed:
            if "metadata" not in item:
                item["metadata"] = {}
                
        return compressed

hybrid_retriever = HybridRetriever()
