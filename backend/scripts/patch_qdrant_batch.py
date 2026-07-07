import os

file_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\vector\qdrant_client.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add embed_texts method
embed_texts_code = """
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self._load_embed_model()
        if not self._embed_model:
            logger.warning("Embedding model not loaded, returning empty vectors.")
            return [[0.0] * 384 for _ in texts]
        
        start = time.time()
        # Batch encode with batch_size=64 and normalize
        embeddings = self._embed_model.encode(texts, batch_size=64, normalize_embeddings=True)
        dur = time.time() - start
        logger.info(f"Embedded {len(texts)} chunks in {dur:.2f}s")
        return embeddings.tolist()
"""

# Inject before embed_text
if "    def embed_text(" in content:
    content = content.replace("    def embed_text(", embed_texts_code + "\n    def embed_text(")

# Replace upsert_chunks logic
import re

old_upsert = """        for chunk in chunks:
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
            qdrant_ids.append(q_id)"""

new_upsert = """        texts = [chunk.get("text", "") for chunk in chunks]
        vectors = self.embed_texts(texts)

        for chunk, vector in zip(chunks, vectors):
            text = chunk.get("text", "")
            doc_id = chunk.get("doc_id")
            page = chunk.get("page", 1)
            chunk_index = chunk.get("chunk_index", 0)
            meta = chunk.get("metadata", {})

            # Generate stable UUID for qdrant if not provided
            q_id = chunk.get("qdrant_id")
            if not q_id:
                q_id = str(uuid.uuid4())
            
            payload = {
                "text": text,
                "tenant_id": tenant_id,
                "doc_id": doc_id,
                "page": page,
                "chunk_index": chunk_index,
                "metadata": meta
            }

            points.append(PointStruct(id=q_id, vector=vector, payload=payload))
            qdrant_ids.append(q_id)"""

content = content.replace(old_upsert, new_upsert)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched qdrant_client.py")
