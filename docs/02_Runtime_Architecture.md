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
│   ├── graph/
│   │   ├── graph_builder.py      # Inserts nodes & relationships to Neo4j
│   │   └── neo4j_client.py       # Queries Cypher properties
│   ├── ingestion/
│   │   ├── document_processor.py # Extracts text via PyMuPDF/Tesseract
│   │   └── entity_extractor.py   # Extracts JSON entities using LLM
│   ├── routers/
│   │   ├── dashboard.py          # System stats & audit log feeds
│   │   ├── engineers.py          # Person/Engineer node lookups
│   │   └── risk.py               # Risk indexes & decay timelines
│   ├── tasks/
│   │   ├── celery_app.py         # Broker, task registrations
│   │   └── ingestion_tasks.py    # Process and delete background tasks
│   └── app.py                    # Fast API server declaration & middleware
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
*   **Tenants Table**: `id (UUID)`, `name`, `slug`, `plan`, `is_active`, `created_at`.
*   **Users Table**: `id (Int)`, `tenant_id (FK)`, `username`, `email`, `hashed_password`, `role`.
*   **Documents Table**: `id (Int)`, `tenant_id (FK)`, `filename`, `file_path`, `file_type`, `status`.
*   **Processing Jobs Table**: `id (UUID)`, `tenant_id (FK)`, `document_id (FK)`, `status`, `error`, `details`.
*   **Chunks Table**: `id (Int)`, `tenant_id (FK)`, `document_id (FK)`, `page_number`, `chunk_index`, `text_content`, `qdrant_id`.

### 3.2 Property Graph Structure (Neo4j)
*   **Nodes**: `Asset`, `Equipment`, `Person`, `Incident`, `Procedure`, `Regulation`, `MissingCategory`.
*   **Edges**: `FOLLOWS`, `MAINTAINED_BY`, `AFFECTED`, `GOVERNED_BY`, `HAS_KNOWLEDGE_GAP`.

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
