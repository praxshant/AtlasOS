# AtlasOS Verification & Operations Manual (Version 2.0)

> **Classification:** Confidential Internal Operations Documentation  
> **Target Audience:** Site Reliability Engineers (SREs), Systems Administrators, DevOps Engineers, and Security Personnel.

---

## 1. Startup Verification & System Bring-Up

This section details the manual verification commands, expected responses, failure conditions, and recovery steps needed to bring up AtlasOS in any environment.

### 1.1 Dependency Verification Checklist

| Dependency | Port | Check Command | Expected Output | Mitigation on Failure |
| :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL** | 5432 | `docker exec -it atlasos-postgres psql -U postgres -d atlasos -c "SELECT 1;"` | `?column? \n ---------- \n 1` | Run `docker compose start postgres`. Verify host port mapping or container health logs. |
| **Redis** | 6379 | `docker exec -it atlasos-redis redis-cli ping` | `PONG` | Run `docker compose start redis`. Check memory limits. |
| **Qdrant** | 6333 | `curl -s http://localhost:6333/collections` | `{"result":{"collections":[...]}}` | Run `docker compose start qdrant`. Check storage space constraints. |
| **Neo4j** | 7687 | `curl -sI http://localhost:7474` | `HTTP/1.1 200 OK` (Web Console) | Run `docker compose start neo4j`. Check java heap allocation limits. |

### 1.2 Application Core Verification

| Service | Check Command | Expected Output | Mitigation on Failure |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend** | `curl -s http://localhost:8000/api/health` | `{"status":"healthy","service":"ATLASOS API"}` | Verify environment variables (`.env`). Ensure PostgreSQL port matches the configuration. |
| **Vite Frontend** | `curl -sI http://localhost:5173` | `HTTP/1.1 200 OK` | Verify local Node modules (`npm install`). Check for typescript compilation errors. |
| **Celery Worker** | `celery -A backend.tasks.celery_app status` | `celery@localhost: OK` | Ensure virtual environment is active. Verify broker connection in `.env`. |

### 1.3 Unified Database Verification Script
Before starting the API backend or Celery tasks, run the unified verification script to assert connection health, check database credentials, and list initialized indices:
```bash
python scripts/verify_databases.py
```

---

## 2. API Integration & Runtime Routing Matrix

All client-to-server communications are prefix-mapped to `/api` and routed via a Vite proxy mapping.

| Client Flow | UI Entry Component | API Route | Backend Service | Target Databases | Verification Method |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **User Authentication** | [Login.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/Login.tsx) | `POST /api/auth/login` | `backend/utils/auth.py` | PostgreSQL | Request valid token and verify it stores to local storage. |
| **Document Upload** | [Documents.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/Documents.tsx) | `POST /api/upload` | `backend/tasks/ingestion_tasks.py` | PostgreSQL, Qdrant, Neo4j | Upload PDF; trace progress bar (`pending` -> `completed`). |
| **System Dashboard** | [Dashboard.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/Dashboard.tsx) | `GET /api/dashboard` | `backend/routers/dashboard.py` | PostgreSQL, Neo4j, Qdrant | Renders health badges and document/node counters. |
| **Knowledge Graph** | [KnowledgeGraph.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/KnowledgeGraph.tsx) | `GET /api/graph/data` | `backend/graph/neo4j_client.py` | Neo4j | Verify force-directed nodes and relationships render. |
| **Graph Node Expansion** | [KnowledgeGraph.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/KnowledgeGraph.tsx) | `GET /api/graph/expand/{node_name}` | `backend/graph/neo4j_client.py` | Neo4j | Click node; verify neighbors load and merge dynamically. |
| **Copilot Chat** | [Copilot.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/Copilot.tsx) | `POST /api/copilot/query` | `backend/agents/copilot_agent.py` | Qdrant, Neo4j | Send question; verify streaming token flow, citations, and graph paths. |
| **RCA State Machine** | [RCA.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/RCA.tsx) | `POST /api/rca/run` | `backend/agents/rca_agent.py` | Qdrant, Neo4j | Submit incident; verify Ishikawa cause tree renders. |
| **Compliance Audit** | [Compliance.tsx](file:///c:/Users/ACER/OneDrive/Desktop/AtlasOS/frontend/src/pages/Compliance.tsx) | `POST /api/compliance/check` | `backend/agents/compliance_agent.py` | Qdrant, Neo4j | Run audit; verify Pass/Fail badges and recommendations render. |

---

## 3. Disaster Recovery & Emergency Operations

### 3.1 Stuck Background Job Recovery
If Celery ingestion jobs remain `pending` or `processing` due to an unexpected worker crash:
1. Identify the stuck job UUIDs in the database:
   ```sql
   SELECT id, document_id, status FROM processing_jobs WHERE status IN ('pending', 'processing');
   ```
2. Run the recovery/purge script to reset stuck jobs:
   ```bash
   python scripts/purge_stuck.py
   ```
3. Restart the Celery worker process to resume processing:
   ```bash
   celery -A backend.tasks.celery_app worker --loglevel=info -P solo
   ```

### 3.2 Database Desynchronization Cleanup
If Postgres metadata exists but associated Qdrant vectors or Neo4j nodes are missing/corrupted:
1. Run a full system wipe and re-migration of databases:
   ```bash
   python backend/scripts/clean_all.py
   ```
2. Bootstrap the default tenant database records:
   ```bash
   python -c "from backend.db.postgres import ensure_default_tenant; ensure_default_tenant()"
   ```
3. Re-upload raw files from the document interface.

### 3.3 Bootstrapping & Seeding Demo Data
To bootstrap the database schema and ingest a pre-packaged suite of industrial documentation (manuals, incident reports, shift handovers) for local demonstration and verification:
```bash
python scripts/bootstrap_demo.py
```
This script automates:
1. Re-migrating PostgreSQL and seeding the default organization tenant.
2. Generating and validating Neo4j index constraints.
3. Iterating and processing the default document registry, creating embeddings in Qdrant, and inserting consolidated nodes/edges in Neo4j.

---

## 4. Observability & SRE Operations

### 4.1 Request Tracing & Correlation
*   All FastAPI endpoints inject an `X-Correlation-ID` header into every response.
*   This correlation ID is preserved across thread pools, async functions, and Celery background workers, allowing end-to-end tracing in log management platforms (Loki, Datadog).

### 4.2 Logging Standards
*   **Format**: Structured JSON logging.
*   **Locations**:
    *   Backend log files are configured through `backend/utils/logging_config.py`.
    *   Vite frontend errors are logged via browser console telemetry.
*   **Error Level Policy**:
    *   `INFO`: Normal operation transactions (e.g. `User registration success`, `Embedding initialized`).
    *   `WARNING`: Recoverable failures (e.g. `Rate limit triggered`, `Redis connection timeout - falling open`).
    *   `ERROR`: Non-recoverable failures (e.g. `Celery execution failure`, `Database transaction rollback`).

---

## 5. Pipeline Evaluation & Testing Suite

AtlasOS features a dedicated testing and evaluation framework to profile system accuracy, retrieval quality, and response latency.

### 5.1 Running the Evaluator
To run the full evaluation suite covering retrieval, graph construction, extraction recall, and answer synthesis:
```bash
python -m backend.eval
```
Individual evaluator modules can also be executed:
*   **Answer Synthesis**: `python backend/eval/answer_eval.py`
*   **Compliance Agent**: `python backend/eval/compliance_eval.py`
*   **Entity Extraction**: `python backend/eval/extraction_eval.py`
*   **Graph Construction**: `python backend/eval/graph_eval.py`
*   **Retrieval (Hybrid)**: `python backend/eval/retrieval_eval.py`
*   **Pipeline Latency Profiling**: `python backend/eval/latency_eval.py`

### 5.2 Evaluation Outputs
All evaluation runs generate detailed JSON report files in:
`backend/eval/results/eval_report_<timestamp>.json`
These files record execution metrics, retrieval recall/precision, entity mismatch rates, and total execution latencies. (Note: These results are ignored by Git configuration).
