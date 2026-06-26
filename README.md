# ATLASOS — Industrial Knowledge Intelligence Platform

ATLASOS is a state-of-the-art industrial operations intelligence platform. It ingests documents (such as SOPs, manuals, incidents logs, and regulations), parses them into semantic chunks, extracts entities/relationships using LLMs via OpenRouter, and populates a unified knowledge model spanning PostgreSQL (operational), Qdrant (vector storage), and Neo4j (knowledge graph).

Reasoning over this database is performed by specialized LangGraph state machines:
1. **Expert Copilot**: Answering operational queries.
2. **Root Cause Analysis (RCA)**: Compiling probable cause chains and confidence metrics from incidents.
3. **Compliance Intelligence**: Reviewing compliance gap metrics.
4. **Lessons Learned Engine**: Generating prevention reports from historical logs.

---

## Directory Structure

```
atlasos/
├── backend/
│   ├── app.py                    ← FastAPI entrypoint
│   ├── config.py                 ← All env vars and settings
│   ├── worker.py                 ← Redis async worker
│   ├── ingestion/
│   │   ├── document_processor.py ← PDF chunking pipeline
│   │   └── entity_extractor.py   ← NER + relationship LLM extractor
│   ├── graph/
│   │   ├── neo4j_client.py       ← Neo4j cypher client
│   │   └── graph_builder.py      ← Neo4j node/edge builder
│   ├── vector/
│   │   └── qdrant_client.py      ← Qdrant embedding + retrieval
│   ├── agents/
│   │   ├── copilot_agent.py      ← Expert copilot state machine
│   │   ├── rca_agent.py          ← RCA cause-tree builder
│   │   ├── compliance_agent.py   ← Compliance gap detector
│   │   └── lessons_agent.py      ← Preventative pattern extractor
│   ├── db/
│   │   └── postgres.py           ← SQLAlchemy operational database models
│   └── utils/
│       └── llm_client.py         ← Unified OpenRouter API wrapper
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx              ← Dashboard
│   │   ├── copilot/page.tsx      ← Copilot Chat Interface
│   │   ├── rca/page.tsx          ← RCA Report Panel
│   │   ├── compliance/page.tsx   ← Compliance Gap Tracker
│   │   └── graph/page.tsx        ← Knowledge Graph explorer
│   └── components/
│       ├── ChatInterface.tsx     ← Chat component
│       ├── DocumentUpload.tsx    ← Document upload widget
│       └── GraphViewer.tsx       ← Canvas force-directed graph view
│
├── docker-compose.yml             ← DB infrastructure (Postgres, Neo4j, Qdrant, Redis)
└── README.md
```

---

## Startup Guide

### 1. Run Core Infrastructure Databases
Ensure Docker is running, then run:
```bash
docker-compose up -d
```
This spins up:
- PostgreSQL on `localhost:5432` (user/pass: `postgres/postgres`, db: `atlasos`)
- Neo4j on `localhost:7474` (HTTP) and `7687` (Bolt) (user/pass: `neo4j/password123`)
- Qdrant on `localhost:6333`
- Redis on `localhost:6379`

### 2. Configure Environment Variables
Create a `.env` file in the `backend/` directory or root workspace containing:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/atlasos
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=openrouter/free
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
```

### 3. Setup Python Backend
Install python requirements:
```bash
pip install -r requirements.txt
```
Start the worker (ingestion processor):
```bash
python backend/worker.py
```
Start the FastAPI server:
```bash
uvicorn backend.app:app --reload --port 8000
```

### 4. Setup Next.js Frontend
Navigate to `frontend/`:
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` to interact with ATLASOS.
