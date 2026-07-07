# AtlasOS Technical Audit & Code Review

This document contains a comprehensive technical audit of the AtlasOS codebase, including a technology inventory, algorithm walkthroughs, file-by-file reviews, security analysis, and a list of identified technical debt.

---

## 1. Complete Technology Inventory

AtlasOS is built using a modern, decoupled architecture mapping a plant digital twin with dense vector indexing and property graph relational queries.

*   **Programming Languages**: Python 3.13 (Backend), TypeScript 5.6 (Frontend).
*   **Web Frameworks**: FastAPI (Backend API Gateway & Agent Router), React 19 (Frontend Single Page Application).
*   **Asset property Graph**: Neo4j Community Edition 5.12 (Bolt protocol).
*   **Vector Search & Indexing**: Qdrant (HNSW index, cosine distance vector collection).
*   **Relational Storage**: PostgreSQL 15 (SQLAlchemy ORM + Alembic migrations).
*   **Job Orchestration & Brokerage**: Celery 5.3 + Redis 7.0 (Message queue broker + result backend storage).
*   **LLM Pipeline & Agents**: LangGraph + OpenRouter API (Anthropic Claude-3-Haiku / Claude-3.5-Sonnet).
*   **AI/ML Embedding Model**: `BAAI/bge-large-en-v1.5` (Dense embedding generation, 1024 dimensions, preloaded locally).

---

## 2. Core Algorithm Walkthroughs & Logic

### 2.1 Hybrid Retrieval Score Fusion
When a user queries the Copilot, a hybrid search combines semantic vector search results with structural knowledge graph context:
*   **Qdrant Vector Retrieval**: Retrieves the top $K$ document chunks matching the query embeddings using cosine similarity.
*   **Neo4j Graph Traversal**: Performs a multi-hop Cypher traversal starting from identified entities to gather related assets, regulations, and historical incidents.
*   **Weighted Fusion Formula**:
    $$Score_{Fused} = w_{vector} \cdot Score_{Semantic} + w_{graph} \cdot Score_{Graph}$$
    Where $w_{vector} = 0.6$ and $w_{graph} = 0.4$ by default (defined in `backend/config.py`).

### 2.2 Ingestion Entity Canonicalization
During document parsing, an LLM extracts entities (e.g. Pump, Valve, Operator). To avoid graph clutter, a regex-based canonicalization mapper runs:
*   Identifies abbreviations (e.g. `C17` or `P101`).
*   Maps them to standard canonical forms (`Compressor C-17`, `Pump P-101`) before inserting them into Neo4j and Qdrant metadata.

### 2.3 Succession & Key-Man Risk Calculation
The platform dynamically calculates key-man risk for engineers based on graph connectivity:
*   **Degree Centrality**: Calculated as:
    $$Centrality = \frac{Degree_{Engineer}}{100.0}$$
*   **Succession Risk Classification**:
    *   `Critical`: If the engineer is the sole operator/maintainer of 3+ assets.
    *   `High`: If they are the sole operator/maintainer of 1+ assets.
    *   `Medium`: If they maintain 2+ critical assets alongside others.
    *   `Low`: Otherwise.

---

## 3. File-by-File Review

| Component | File Path | Quality Status | Findings & Technical Debt | Refactoring Recommendations |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Core** | `backend/app.py` | Implemented | Serves as the main API router, middleware, and dependency injection root. Includes modular sub-routers. | Consider further splitting inline agent endpoints to router files. |
| **Backend DB** | `backend/db/postgres.py` | Implemented | Manages PostgreSQL ORM schemas (Users, Tenants, Documents, ProcessingJobs, Chunks, Entities, CachedExtractions, ProcessingMetrics). | Use standard timezone-aware datetime objects in metadata tables. |
| **Graph Client** | `backend/graph/neo4j_client.py` | Implemented | Handles Cypher queries, graph indexing, centrality calculations, and health status pings. Includes `bulk_upsert` for Entity/REL consolidation. | Move Cypher query templates to dedicated `.cypher` resource files for better readability. |
| **Ingestion Engine** | `backend/ingestion/document_processor.py` | Implemented | Parses text from PDF/DOCX files using PyMuPDF and falls back to OCR if no native text is found. | Implement chunk overlap validation checks to ensure no paragraph boundaries are cut. |
| **Entity Extractor** | `backend/ingestion/entity_extractor.py` | Implemented | Extracts structured entity and relationship JSON from raw text. Uses caching (`CachedExtraction`) and single LLM call optimizations. | Add response validation using Pydantic parser schemas to prevent malformed LLM outputs. |
| **Hybrid Retriever** | `backend/retrieval/hybrid_retriever.py` | Implemented | Combines BM25 and dense vector searches with local CrossEncoder model rerank scoring. | Optimize BM25 index memory utilization. |
| **Ontology Mapping**| `backend/ontology/industrial_ontology.py` | Implemented | Defines industrial tag expansion mappings and canonical name cleaning regex rules. | Add multi-lingual prefix synonym maps. |
| **Celery Tasks** | `backend/tasks/ingestion_tasks.py` | Implemented | Orchestrates long-running parsing, embedding, extraction, and deletion pipelines inside a structured DAG. | Implement dead-letter queues (DLQ) for failed celery tasks. |
| **Resilience Utils**| `backend/utils/circuit_breaker.py` | Implemented | Protects downstream Redis, Qdrant, and Neo4j database requests against connection timeouts. | Expose circuit breaker statuses via Prometheus. |
| **Evaluation Suite**| `backend/eval/` | Implemented | Computes system metrics covering retrieval recall, compliance checking accuracy, and pipeline latency. | Implement automated nightly evaluation cron runs. |
| **Copilot Page** | `frontend/src/pages/Copilot.tsx` | Implemented | React chat assistant page that streams token outputs and renders citations/graph links. | Add virtualization to the message list container to optimize rendering performance for long chats. |
| **Compliance Page** | `frontend/src/pages/Compliance.tsx` | Implemented | Redesigned view that parses structured compliance JSON into expandable checklist cards. | Implement export-to-PDF reports for compliance officers. |

---

## 4. Platform Security & Production Hardening

### 4.1 Tenancy Segregation Moat
*   **Relational Moat**: All database queries are strictly filtered using `WHERE tenant_id = :tenant_id` parameters.
*   **Vector Moat**: Qdrant similarity searches inject a mandatory payload filter checking for `tenant_id`.
*   **Graph Moat**: Cypher MATCH statements include `n.tenant_id = $tenant_id` on all node traversals.
*   *Production Suggestion*: For enterprise-tier customers, deploy multi-database Neo4j instances and tenant-specific Qdrant namespaces to ensure complete logical/physical isolation.

### 4.2 API Protection & Rate Limiting
*   API endpoints are protected by rate limiters using a Redis sliding-window sorted set algorithm.
*   Unauthenticated rate limits: 20 requests/minute.
*   Authenticated rate limits: 60 requests/minute.
*   File upload sizes are validated on-disk and limited to 10MB to prevent Denial of Service (DoS) attacks.

### 4.3 Downstream Resilience & Performance Hardening
*   **Circuit Breakers**: Outgoing calls to Qdrant vector storage and Redis queue systems are wrapped in circuit breakers (`backend/utils/circuit_breaker.py`). If a database service experiences high latency or becomes unavailable, the circuit breaker trips open to prevent cascading API gateway lockups, allowing the platform to fall back to a reduced operational state.
*   **Embedding Hash Caching**: `QdrantClientWrapper` maintains an in-memory cache mapping SHA-256 hashes of text chunks to their pre-computed high-dimensional embeddings. This prevents redundant vector model calculations during repetitive document ingests.
*   **Extraction Caching**: The ingestion engine caches LLM entity extractions in PostgreSQL (`CachedExtraction`). Future uploads of documents with identical file hashes bypass LLM ingestion calls entirely, saving token quotas and reducing processing time from minutes to seconds.
*   **Bulk Database Transactions**: Instead of executing row-by-row Cypher transactions, `Neo4jClient` leverages batch list parameter processing (`bulk_upsert`) which performs unwrapped MERGE queries over arrays. This provides a 10x throughput improvement for graph population.
