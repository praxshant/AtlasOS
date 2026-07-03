# AtlasOS Platform Roadmap & Engineering Backlog (Version 2.0)

> **Classification:** Confidential Internal Platform Documentation  
> **Target Audience:** Product Managers, Technical Leads, Platform Engineers, and Dev Teams.

---

## 1. Product State & Completeness Matrix

This matrix evaluates the production readiness of each module in the AtlasOS ecosystem.

| Module | Subsystem | Completion State | Reasoning |
| :--- | :--- | :--- | :--- |
| **Authentication** | User Sign-In & Guards | **Production Ready** | Secure cookies, JWT verification, and active router guard mappings are implemented in the React-Vite SPA. |
| **Ingestion** | PyMuPDF parsing & OCR | **Implemented** | Resolves PDF/DOCX structures and runs Tesseract when raw texts are missing. |
| **Extraction** | LLM Entity Extractor | **Implemented** | Deduplicates entity abbreviations to canonical forms prior to storing them. |
| **Knowledge Graph** | Neo4j property models | **Implemented** | Indices, entity constraints, and path expansion are verified and active. |
| **GraphRAG** | Fusion retrieve pipeline | **Implemented** | Streams tokens, citations, and graph mappings successfully. |
| **RCA** | Ishikawa Cause tree | **Implemented** | Renders dynamic causal chains in UI instead of raw JSON dumps. |
| **Compliance** | Audit checker page | **Implemented** | Renders Pass/Fail checklist cards with highlighted regulatory non-compliance findings. |
| **DevOps** | Docker Compose bring-up | **Production Ready** | All dependency databases are fully containerized and restart automatically. |

---

## 2. Engineering Backlog

This backlog lists the outstanding work prioritized by business impact.

### 2.1 Critical Priority (P0)
*   **Asynchronous Model Load Optimization**: Avoid loading the HuggingFace `SentenceTransformer` model synchronously inside the API thread pool on startup. This causes the uvicorn start to exceed 60 seconds. Refactor to load the model asynchronously in a background thread or spin up a dedicated embedding microservice.
*   **Alembic Migration Verification**: Ensure all schema updates (like the `processing_jobs.details` JSONB column) are packaged into standard Alembic migration scripts rather than relying on on-startup metadata creation checks.

### 2.2 High Priority (P1)
*   **Virtual list rendering in Copilot Chat**: Prevents DOM slowdowns when chats exceed 100+ messages.
*   **CSV/XLSX Ingestion support**: Build dedicated spreadsheet parsers inside `document_processor.py` to allow bulk loading of asset tags.

### 2.3 Medium Priority (P2)
*   **SSO Integration**: Add support for OpenID Connect (OIDC) / SAML 2.0 logins.
*   **Graph Export Utilities**: Allow reliability engineers to download the generated Neo4j subgraphs as standard GML or JSON formats.

---

## 3. Platform Cleanup & Legacy Retirement Log

As part of the final production hardening, all dead, unused, and legacy scrap codes are retired to reduce package sizes and cognitive load for new developers.

### 3.1 Cleanup Log

| Path | File Type | Status | Justification for Deletion |
| :--- | :--- | :--- | :--- |
| **`scripts/frontend_legacy/`** | Directory | **Retired** | Dead Next.js project code. Superseded by the active React-Vite SPA in `frontend/`. |
| **`scripts/stitch_remix_of_fleet_admin_dashboard/`** | Directory | **Retired** | Obsolete layout prototyping experiments. Unused in production. |
| **`docs/03_Verification_Masterplan.md`** | File | **Retired** | Consolidated into `03_Verification_and_Operations.md`. |
| **`docs/04_Production_Checklist.md`** | File | **Retired** | Consolidated into `03_Verification_and_Operations.md`. |
| **`docs/05_Technical_Debt.md`** | File | **Retired** | Consolidated into `04_Technical_Audit.md`. |
| **`docs/06_Roadmap.md`** | File | **Retired** | Consolidated into `05_Roadmap_and_Engineering_Backlog.md`. |

---

## 4. Release Milestones & Enterprise Target Dates

*   **Milestone 1 (v2.1.0) - SRE Bring-up**: Complete doc consolidation, repository cleanup, and README rewrites. (Target: Immediate).
*   **Milestone 2 (v2.2.0) - Pilot Staging**: Implement async model load and verify Alembic migrations. (Target: End of Month).
*   **Milestone 3 (v2.3.0) - Enterprise Beta**: Multi-database Neo4j configuration, SAML 2.0 SSO, and PDF reports export. (Target: Next Quarter).
