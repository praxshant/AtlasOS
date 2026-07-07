# AtlasOS Runtime Architecture

This document maps the actual runtime codebase, database schemas, API schemas, and observability layers of AtlasOS.

---

## 1. Directory Tree & Components

```
AtlasOS/
├── backend/                      # FastAPI Python Application
│   ├── agents/                   # LLM Agent Implementations
│   │   ├── compliance_agent.py   # Audits text chunks against regulations
│   │   ├── copilot_agent.py      # Core GraphRAG pipeline & context builder
│   │   ├── lessons_agent.py      # Synthesizes patterns from logs
│   │   └── rca_agent.py          # Builds fault trees from descriptions
│   ├── db/
│   │   └── postgres.py           # Database models, schemas, and session configs
│   ├── eval/                     # Model and Pipeline Evaluation Framework
│   │   ├── answer_eval.py        # LLM response quality metric evaluator
│   │   ├── compliance_eval.py    # Audits compliance agent accuracy
│   │   ├── extraction_eval.py    # Evaluates entity extraction recall
│   │   ├── graph_eval.py         # Evaluates property graph construction
│   │   ├── retrieval_eval.py     # Evaluates semantic and BM25 retrievers
│   │   └── latency_eval.py       # Profiles performance latency across DB pipelines
│   ├── graph/
│   │   ├── graph_analytics.py    # Computes PageRank and centrality metrics
│   │   ├── graph_builder.py      # Inserts nodes & relationships to Neo4j
│   │   ├── graph_health.py       # Graph database health statistics collector
│   │   └── neo4j_client.py       # Queries Cypher properties & handles bulk upserts
│   ├── ingestion/
│   │   ├── document_processor.py # Extracts text via PyMuPDF/Tesseract
│   │   └── entity_extractor.py   # Extracts JSON entities using LLM (One-Call/Regex/Cache)
│   ├── ontology/
│   │   └── industrial_ontology.py# Industrial ontology canonicalization definitions
│   ├── retrieval/
│   │   └── hybrid_retriever.py   # Retriever 3.0 (semantic vectors + BM25 keyword search)
│   ├── routers/
│   │   ├── analytics.py          # Exposes graph topology & centrality metrics
│   │   ├── dashboard.py          # System stats & audit log feeds
│   │   ├── engineers.py          # Person/Engineer node lookups
│   │   ├── graph_health.py       # Graph health diagnostics endpoint
│   │   ├── ingestion_health.py   # Celery worker and queue health status
│   │   └── risk.py               # Risk indexes & decay timelines
│   ├── services/
│   │   └── graph_analytics.py    # Business logic for graph metrics
│   ├── tasks/
│   │   ├── celery_app.py         # Broker, task registrations
│   │   ├── ingestion_tasks.py    # Process and delete background tasks (Celery DAG)
│   │   └── progress_tracker.py   # Tracks background tasks progress in Redis
│   ├── utils/
│   │   ├── circuit_breaker.py    # Resilient circuit breakers for database failures
│   │   ├── llm_provider.py       # LLM provider wrapper for OpenRouter & Ollama
│   │   └── ...                   # Startup checks, metrics, rate limiting
│   └── app.py                    # FastAPI server declaration & middleware
└── frontend/                     # React 19 Vite Application
    ├── src/
    │   ├── api/                  # API client wrapper (`client.ts`)
    │   ├── components/           # Shell Layouts & UI primitives
    │   ├── pages/                # Pages (Dashboard, Documents, RCA, etc.)
    │   └── store/                # Zustand client stores (`index.ts`)
```

---

## 2. API Schema Definition

All endpoints are prefix-mapped to `/api` via Vite dev proxies.

### 2.1 Authentication & Tenancy
*   `POST /api/auth/register`: Expects `{username, name, email, password, role}`. Hashes password using PBKDF2.
*   `POST /api/auth/login`: Expects `{email, password}`. Returns `{access_token, token_type, role, username}`.

### 2.2 Document Intelligence
*   `POST /api/upload`: Receives multipart form data file. Enqueues background parsing task and returns job UUID.
*   `GET /api/jobs/{job_id}`: Retrieves ingestion success/error states and entity counts.
*   `GET /api/documents`: Fetches list of active documents for the active tenant.
*   `DELETE /api/documents/{document_id}`: Dispatches background Celery job to purge data.

### 2.3 Graph & Vectors
*   `GET /api/graph/data`: Retrieves Neo4j property nodes and relationship vectors.
*   `GET /api/graph/expand/{node_name}`: Returns the 2-hop neighborhood of a clicked node.

### 2.4 Agent Services
*   `POST /api/copilot/query`: Streams structured text chunks and JSON citations via Server-Sent Events (SSE).
*   `POST /api/rca/run`: Submits an incident description and returns Ishikawa causal nodes.
*   `POST /api/compliance/check`: Runs compliance review on a selected document.

---

## 3. Database Schema Overview

### 3.1 Relational Models (PostgreSQL)
*   **Tenants Table** (`tenants`): `id (UUID)`, `name`, `slug`, `plan`, `is_active`, `created_at`.
*   **Users Table** (`users`): `id (Int)`, `tenant_id (FK)`, `username`, `email`, `hashed_password`, `role`.
*   **Documents Table** (`documents`): `id (Int)`, `tenant_id (FK)`, `filename`, `file_path`, `file_type`, `status`.
*   **Processing Jobs Table** (`processing_jobs`): `id (UUID)`, `tenant_id (FK)`, `document_id (FK)`, `status`, `error`, `details (JSONB)`.
*   **Chunks Table** (`chunks`): `id (Int)`, `tenant_id (FK)`, `document_id (FK)`, `page_number`, `chunk_index`, `text_content`, `qdrant_id (UUID)`.
*   **Audit Logs Table** (`audit_logs`): `id (Int)`, `tenant_id (FK)`, `user_id (FK)`, `actor_type`, `actor_name`, `action`, `query_text`, `timestamp`, `details`.
*   **Entities Table** (`entities`): `id (Int)`, `tenant_id (FK)`, `canonical_name`, `entity_type`, `confidence`, `source_doc_id (FK)`, `created_at`.
*   **Entity Relationships Table** (`relationships`): `id (Int)`, `tenant_id (FK)`, `source_entity`, `target_entity`, `relationship_type`, `confidence`, `chunk_index`, `source_doc_id (FK)`, `created_at`.
*   **Cached Extractions Table** (`cached_extractions`): `id (Int)`, `file_hash (Unique)`, `provider`, `llm_json`, `version`, `created_at`.
*   **Processing Metrics Table** (`processing_metrics`): `id (Int)`, `document_id (FK)`, `parse_time_ms`, `embed_time_ms`, `llm_time_ms`, `graph_time_ms`, `total_time_ms`, `created_at`.

### 3.2 Property Graph Structure (Neo4j)
*   **Nodes**: `:Entity` (unified node label) with properties: `tenant_id`, `canonical_id`, `name`, `type` (maps to entity type: `Asset`, `Equipment`, `Person`, `Incident`, `Procedure`, `Regulation`, `MissingCategory`), `confidence`, `extraction_method`, `updated_at`.
*   **Edges**: `:REL` (unified edge relationship type) with properties: `tenant_id`, `rel_type` (maps to relationship: `FOLLOWS`, `MAINTAINED_BY`, `AFFECTED_BY`, `GOVERNED_BY`, `HAS_KNOWLEDGE_GAP`), `confidence`, `document_id`, `updated_at`.
*   **Constraints**: Unique database constraint on `(:Entity {tenant_id, canonical_id})` to ensure multi-tenant entity integrity and high-performance lookup indexes.

---

## 4. Observability & Observability Metrics

### 4.1 Correlation ID Middleware
FastAPI captures or generates a unique UUID for every incoming HTTP request inside the context middleware:
```python
corr_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
set_correlation_id(corr_id)
```
This ID is attached to the headers of the response and injected into every log string compiled by backend engines.

### 4.2 Logging Configuration
The system sets up standard JSON logging outputs, ensuring structured logs are easily parsed by aggregators (e.g. Loki, Datadog):
*   `INFO`: Startup checks, completed database migrations, token generation.
*   `WARNING`: Stats enrichment failures, database retries, slow queries.
*   `ERROR`: Celery task exceptions, Neo4j timeouts, PyJWT decryption failures.

### 4.3 Metrics Endpoint
*   `GET /api/metrics`: Exposes Prometheus metrics covering API response latency, connection pool counts, and Celery tasks enqueued/failed.

---

## 5. Ingestion Pipeline DAG Workflow

Document processing is managed as a Celery DAG (Directed Acyclic Graph) workflow chain to guarantee transactional consistency and failure isolation:

```
[validate_task] ──► [parse_and_chunk_task] ──► [embed_task] ──► [extract_entities_task] ──► [quality_validation_task]
```

1. **`validate_task`**: Verifies document integrity, file structure, and extracts initial validation metadata.
2. **`parse_and_chunk_task`**: Processes files (using PyMuPDF or Tesseract OCR for PDFs/images) into text chunks. Enriches processing jobs with risk signals.
3. **`embed_task`**: Generates high-dimensional vector embeddings using the locally preloaded `BAAI/bge-large-en-v1.5` model, pushing vectors to Qdrant.
4. **`extract_entities_task`**: Optimizes processing by running a single LLM extraction query per document instead of per-chunk calls. It combines deterministic regex checks with structured LLM extractions, checks for cached extractions in PostgreSQL (`CachedExtraction`), and updates Neo4j in a single bulk transaction (`neo4j_client.bulk_upsert`).
5. **`extract_relationships_task` & `graph_upsert_task`**: Handled dynamically and inline by the entities task to reduce overhead (currently configured as pass-throughs).
6. **`quality_validation_task`**: Conducts final chunk/node validation checks, persists pipeline stage durations in `ProcessingMetrics`, and updates the processing job to `completed`.

---

## 6. Copilot Agent & Hybrid Retrieval

The `CopilotAgent` incorporates a LangGraph agentic reasoning loop that handles user queries with advanced cognitive features:

*   **Query Classification**: Classifies user intent (`metadata`, `compliance`, `engineer`, `risk`, or `general`) to adjust system routing and prompting context.
*   **Centrality-Aware Ranking**: Performs hybrid ranking across vector hits and graph nodes. Assigns final ranking scores using a formula combining PageRank and graph proximity:
    $$Score_{Fused} = 0.15 \cdot Score_{Proximity} + 0.35 \cdot Score_{PageRank}$$
*   **Shortest Path Context**: Automatically extracts the shortest topological paths between identified entities in Neo4j (using `get_shortest_path`) and injects the raw paths directly into the LLM context.
*   **LLM Fallback Mode**: If OpenRouter quotas are exceeded or request limits fail, the agent yields a structured fallback JSON response compiled entirely from raw vector snippets and matching property graph nodes.
