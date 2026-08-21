# 🦅 Enterprise Multi-Tenant AI & Cognitive RAG Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.116.1-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg?logo=python&logoColor=white)](https://www.python.org)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-red.svg?logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Celery](https://img.shields.io/badge/Celery-Distributed%20Tasks-37814A.svg?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose%20Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Proprietary-yellow.svg)](#)

An enterprise-grade, multi-tenant **Retrieval-Augmented Generation (RAG)** platform and cognitive intelligence gateway. The platform unifies personal document analysis, departmental knowledge silos, and organization-wide data repositories into a single conversational interface governed by zero-leakage Role-Based Access Controls (RBAC), hybrid search, cross-encoder re-ranking, and strict grounding verification.

---

## 🌟 Core Enterprise Capabilities

### 1. 🧠 Single Unified Assistant with Intelligent Query Routing (Option A)
* **Context & Intent Classifier**: Classifies queries into casual conversational chat or multi-source knowledge retrieval.
* **Unified Conversational Gateway**: Users query personal uploads, department documentation, and corporate policies from a single chat interface. The system automatically scopes retrieval across authorized data boundaries.

### 2. 🔐 Multi-Tenancy & Zero-Leakage Payload RBAC
* **Strict Tenant Isolation**: Enforced at both the relational layer (`org_id` foreign keys) and vector store index layer (`must: org_id`).
* **Hierarchical Role Matrix**:
  - `SUPER_ADMIN`: Tenant-wide configuration, persona governance, and audit inspection.
  - `DEPT_ADMIN`: Department knowledge curation, ingestion management, and member oversight.
  - `MEMBER`: Standard query access within assigned department and personal uploads.
  - `AUDITOR`: Read-only access to tamper-evident SIEM audit logs.
* **Data Access Classifications**: `PUBLIC`, `DEPARTMENT`, `CONFIDENTIAL` (Admins only), and `RESTRICTED` (Owner/Session private).

### 3. 🎯 Hybrid Retrieval & Reciprocal Rank Fusion (RRF)
* **Dense Semantic Vector Search**: Embeddings indexed via Qdrant (auto-configured 768d / 1024d vectors).
* **Lexical Keyword Overlap (BM25 Equivalent)**: Guarantees exact matches for SKUs, legal clauses, dates, and technical identifiers.
* **Reciprocal Rank Fusion (RRF)**: Normalizes and merges dense and lexical results using rank position scaling ($k=60$).

### 4. ⚡ Cross-Encoder Re-ranking
* **FlashRank Integration**: In-process CPU-optimized cross-encoder model (`ms-marco-TinyBERT-L-2-v2`) re-scores candidate chunks, boosting context precision and minimizing prompt token bloat.

### 5. 🛡️ Grounding Guardrails & Hallucination Prevention
* **Elimination of Silent Parametric Bypass**: When candidate vector similarity falls below the confidence threshold (`score < 0.35`), the system returns an honest out-of-context response rather than hallucinating from pre-trained weights.
* **Citation Syntax Enforcement**: Enforces inline document citation tags (`[Doc: <filename>]`) on all generated claims.

### 6. 🔄 Asynchronous Multi-Source Ingestion Pipeline
* **Background Worker Processing**: Document parsing, chunking, embedding, and vector upserting offloaded to **Celery + Redis**, keeping HTTP upload responses under 50ms (`202 Accepted`).
* **Heterogeneous Connectors**: Native support for File streams, Amazon S3 buckets, and Relational SQL databases.
* **Multi-Format Parsers**: PDF, Microsoft Word (`.docx`), Markdown (`.md`), Plaintext (`.txt`), CSV, and JSON.

### 7. 🎭 Persona & Prompt Template Governance
* **Assistant Personas**: Department-scoped system instructions with dynamic variables (`{user_name}`, `{department_name}`, `{org_name}`).
* **Prompt Templates**: Reusable, admin-curated prompt templates for Q&A, Summarization, and Policy Analysis.

### 8. 📋 Tamper-Evident SIEM Audit Logging
* **Immutable Compliance Trail**: Every login, document upload, query, and administrative change is permanently logged to PostgreSQL with user ID, tenant ID, and citation provenance metadata.

---

## 🏛️ System Architecture

```
                               ┌────────────────────────────────────────┐
                               │  Client Web UI / REST API / SDK Gateway │
                               └───────────────────┬────────────────────┘
                                                   │
                                                   ▼
                               ┌────────────────────────────────────────┐
                               │   FastAPI Modular Routing Layer        │
                               │  (/auth, /chat, /documents, /gov)      │
                               └───────────────────┬────────────────────┘
                                                   │
                        ┌──────────────────────────┴──────────────────────────┐
                        ▼                                                     ▼
         ┌─────────────────────────────┐                       ┌─────────────────────────────┐
         │  Domain Repositories (CRUD) │                       │ Unified Cognitive           │
         │  (User, Doc, Chat, Gov)     │                       │ Orchestrator & Planner      │
         └──────────────┬──────────────┘                       └──────────────┬──────────────┘
                        │                                                     │
                        ▼                                                     ▼
         ┌─────────────────────────────┐                       ┌─────────────────────────────┐
         │ PostgreSQL Relational DB    │                       │ Knowledge Source Registry   │
         │ (Tenants, RBAC, Audits)     │                       │ & Security Filter Builder   │
         └─────────────────────────────┘                       └──────────────┬──────────────┘
                                                                              │
                        ┌─────────────────────────────────────────────────────┴────────────────────────────────┐
                        ▼                                                     ▼                                ▼
         ┌─────────────────────────────┐                       ┌─────────────────────────────┐  ┌─────────────────────────────┐
         │ Qdrant Dense Vector Store   │                       │ Lexical Keyword Matcher     │  │ Cross-Encoder Re-ranker     │
         │ (Multi-Tenant Collections)  │                       │ & Reciprocal Rank Fusion    │  │ (FlashRank TinyBERT)        │
         └──────────────┬──────────────┘                       └──────────────┬──────────────┘  └──────────────┬──────────────┘
                        │                                                     │                                │
                        └─────────────────────────────────────────────────────┼────────────────────────────────┘
                                                                              ▼
                                                               ┌─────────────────────────────┐
                                                               │ Grounding & Guardrails      │
                                                               │ (Citation & NLI Entailment) │
                                                               └──────────────┬──────────────┘
                                                                              │
                                                                              ▼
                                                               ┌─────────────────────────────┐
                                                               │ LLM Provider Strategy       │
                                                               │ (Gemini / Ollama / vLLM)    │
                                                               └─────────────────────────────┘
```

---

## 📁 Project Directory Structure

```text
AI-Content-Sentiment-Keywords-Gemini-powered/
│
├── app/
│   ├── core/                        # Core infrastructural configurations
│   │   ├── config.py                # Centralized Pydantic Settings & Env validation
│   │   ├── security.py              # JWT tokens, PBKDF2 password hashing & RBAC dependencies
│   │   ├── audit.py                 # Immutable SIEM compliance audit logger
│   │   ├── celery_app.py            # Celery asynchronous task broker configuration
│   │   └── database.py              # SQLAlchemy engine & SessionLocal factory
│   │
│   ├── models/                      # SQLAlchemy database entities
│   │   ├── __init__.py              # Unified model registry for Alembic
│   │   ├── enterprise_models.py     # Organizations, Users, Depts, Docs, Personas, Audits
│   │   ├── rag_chat_models.py       # Conversational chat sessions & messages
│   │   └── content_analyze.py       # Legacy content analysis records
│   │
│   ├── schemas/                     # Pydantic validation & data transfer schemas
│   │   ├── __init__.py
│   │   ├── auth.py                  # Login, registration, and user profile schemas
│   │   ├── chat.py                  # Unified chat query, session, and citation schemas
│   │   ├── document.py              # Document upload, ingestion, and job schemas
│   │   └── governance.py            # Department, Persona, Prompt Template, and Audit schemas
│   │
│   ├── repositories/                # Domain Repository Layer (Clean Persistence)
│   │   ├── __init__.py
│   │   ├── user_repository.py       # Tenant, Department, and User data access
│   │   ├── document_repository.py   # Document metadata and sync job persistence
│   │   ├── chat_repository.py       # Session and message provenance persistence
│   │   └── governance_repository.py # Personas, Prompt Templates, and Audit logs
│   │
│   ├── services/                    # Business logic & AI subsystems
│   │   ├── llm.py                   # Multi-provider LLM Strategy (Gemini, Ollama, vLLM, OpenAI)
│   │   │
│   │   ├── retrieval/               # Retrieval & vector ranking subsystem
│   │   │   ├── vector_store.py      # Qdrant client singleton, indexing & search
│   │   │   ├── security_filter.py   # Mathematical zero-leakage RBAC payload filter builder
│   │   │   ├── hybrid_retriever.py  # Dense + Lexical retrieval with Reciprocal Rank Fusion
│   │   │   └── reranker.py          # FlashRank Cross-Encoder re-ranker
│   │   │
│   │   ├── registry/                # Knowledge source catalog
│   │   │   └── knowledge_registry.py# Source descriptors & user clearance resolvers
│   │   │
│   │   ├── guardrails/              # Safety, Grounding & Template Engine
│   │   │   ├── grounding_validator.py# Citation tag enforcement & out-of-context fallback
│   │   │   └── prompt_engine.py     # Safe dynamic prompt variable interpolation
│   │   │
│   │   └── orchestration/           # Cognitive Orchestration (Option A)
│   │       ├── query_planner.py     # Intent classifier & query decomposition
│   │       └── unified_orchestrator.py # Core RAG orchestrator coordinating pipeline
│   │
│   ├── routes/                      # Modular FastAPI API Routers
│   │   ├── __init__.py
│   │   ├── auth.py                  # /enterprise/auth (Tenant onboard, login, token)
│   │   ├── chat.py                  # /chat/query (Unified Personal & Enterprise RAG)
│   │   ├── documents.py             # /documents (Upload, async ingest, delete)
│   │   ├── governance.py            # /enterprise (Personas, Prompts, Users, Depts)
│   │   ├── jobs.py                  # /enterprise/jobs (S3 / DB Data sync rules)
│   │   ├── audit.py                 # /enterprise/audit (SIEM audit logs)
│   │   └── views.py                 # Jinja2 HTML templates & UI rendering
│   │
│   ├── connectors/                  # Data Ingestion Connectors
│   │   ├── base.py                  # BaseConnector & RawDocument definitions
│   │   ├── file_connector.py        # Multipart file streamer
│   │   ├── s3_connector.py          # AWS S3 object store connector
│   │   └── db_connector.py          # Relational SQL database connector (PostgreSQL/MySQL)
│   │
│   ├── parsers/                     # Multi-Format Document Parsers
│   │   ├── factory.py               # ParserFactory selector
│   │   ├── pdf_parser.py            # PyPDF text extractor
│   │   ├── docx_parser.py           # python-docx table & text extractor
│   │   └── text_parser.py           # Plaintext, Markdown, CSV, JSON parser
│   │
│   ├── tasks/                       # Distributed Celery Ingestion Tasks
│   │   └── ingestion_tasks.py       # Asynchronous document & job background workers
│   │
│   ├── templates/                   # Jinja2 Front-End Templates
│   │   ├── index.html               # Main conversational workspace
│   │   ├── enterprise_dashboard.html# Admin visualizer & telemetry dashboard
│   │   └── login.html               # Sign-in & Tenant onboarding portal
│   │
│   └── main.py                      # Application bootstrap & router registration
│
├── alembic/                         # Database Migration Scripts
├── benchmarking/                    # Verification & Performance Test Suites
├── docker-compose.yml               # Multi-container orchestration (FastAPI, Qdrant, Redis, Celery)
├── Dockerfile                       # Production container build definition
├── requirements.txt                 # Pinned project dependencies
└── .env                             # Environment configuration
```

---

## 🚀 Getting Started & Setup Instructions

### Prerequisites
* **Docker & Docker Compose** (Recommended)
* **Python 3.11+** (if running locally)
* **PostgreSQL 14+**
* **Redis 7+**

---

### 1. Environment Configuration

Create a `.env` file in the project root:

```ini
# PostgreSQL Relational DB
DATABASE_URL=postgresql://postgres:Password#123@host.docker.internal:5432/wings_orgs

# JWT Security
ENTERPRISE_SECRET_KEY=your-production-secret-key-32-chars-minimum
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# LLM Inference Provider (options: gemini, ollama, vllm, openai)
LLM_PROVIDER=ollama

# Ollama Local Config
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=gemma3:12b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b

# Google Gemini Config (if LLM_PROVIDER=gemini)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Qdrant Vector Database
QDRANT_STORAGE=server
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=assistant_knowledge
EMBEDDING_DIMENSION=1024

# Redis Task Broker
REDIS_URL=redis://redis:6379/0
```

---

### 2. Running with Docker Compose (Recommended)

Start all services (FastAPI, Qdrant, Redis, and Celery Ingestion Worker) with a single command:

```bash
docker-compose up -d --build
```

Access the services:
* **Conversational Workspace**: [http://localhost:4500](http://localhost:4500)
* **Enterprise Admin Dashboard**: [http://localhost:4500/enterprise/dashboard](http://localhost:4500/enterprise/dashboard)
* **Interactive API Documentation (Swagger)**: [http://localhost:4500/docs](http://localhost:4500/docs)
* **Qdrant Vector DB Console**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)

---

### 3. Local Manual Execution

If running without Docker:

```bash
# 1. Activate virtual environment
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows

# 2. Run Database Migrations
alembic upgrade head

# 3. Start Celery Ingestion Worker
celery -A app.core.celery_app worker --loglevel=info

# 4. Start FastAPI Application Server
uvicorn app.main:app --host 0.0.0.0 --port 4500 --reload
```

---

## 🧪 Architectural Verification & Testing

Execute the built-in end-to-end architectural test suite to verify configuration loading, domain repositories, decomposed services, hybrid retrieval, intent classification, and grounding guardrails:

```bash
python benchmarking/test_verification.py
```

Expected Output:
```text
Testing imports...
  [PASS] Config loaded: App='Enterprise Multi-Tenant AI & RAG Platform', Version='2.0.0'
  [PASS] Repositories imported successfully.
  [PASS] All decomposed retrieval, guardrail, and orchestration services imported.
  [PASS] All decomposed route modules imported.
  [PASS] FastAPI app initialized successfully with all routes registered.
  [PASS] GroundingValidator transparent fallback asserted correctly.
  [PASS] QueryPlanner conversational detection asserted: GENERAL
  [PASS] QueryPlanner knowledge query routing asserted: KNOWLEDGE_SEARCH

ALL ARCHITECTURAL VERIFICATION CHECKS PASSED SUCCESSFULLY!
```

---

## 📡 REST API Reference

| Tag | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `/enterprise/auth/register-tenant` | Provisions a new Organization, default Department, and SuperAdmin. |
| **Auth** | `POST` | `/enterprise/auth/token` | OAuth2 password flow issuing scoped JWT with Org, Dept & Role claims. |
| **Auth** | `GET` | `/enterprise/auth/me` | Fetches authenticated user profile and permissions. |
| **Chat** | `POST` | `/chat/query` | **Unified RAG Endpoint**: Executes hybrid retrieval, reranking & grounding check. |
| **Chat** | `GET` | `/chat/sessions` | Lists conversational chat sessions scoped to user and tenant. |
| **Chat** | `DELETE`| `/chat/{session_id}` | Deletes chat session and purges associated vector index points. |
| **Docs** | `POST` | `/documents/upload` | Queues document parsing, chunking, and vector indexing via Celery (`202 Accepted`). |
| **Docs** | `GET` | `/documents` | Lists all documents user has clearance to view. |
| **Docs** | `DELETE`| `/documents/{document_id}` | Deletes document and purges Qdrant vector chunks. |
| **Governance**| `GET` | `/enterprise/personas` | Lists Admin-managed Assistant Personas available to the department. |
| **Governance**| `POST`| `/enterprise/personas` | Creates department-scoped Assistant Persona with system prompt template. |
| **Governance**| `GET` | `/enterprise/prompt-templates`| Lists structured prompt templates. |
| **Governance**| `GET` | `/enterprise/departments` | Lists all functional departments in the organization. |
| **Jobs** | `POST` | `/enterprise/jobs/create` | Configures automated S3 bucket or SQL DB sync rules. |
| **Jobs** | `POST` | `/enterprise/jobs/{job_id}/trigger` | Dispatches background Celery job to pull data from external source. |
| **Audit**| `GET` | `/enterprise/audit/logs` | Immutable SIEM compliance audit review (Admins and Auditors only). |

---

## 🛡️ Security & Compliance Standards

* **Zero-Leakage Vector Filtering**: Every Qdrant similarity search mandates an exact `org_id` match and filters by user ACLs at the index level.
* **Cryptographic Provenance**: Document payloads are hashed using SHA-256 to prevent duplicate indexing and tampering.
* **Auditability**: All queries, uploads, and administrative actions emit structured audit records with IP addresses and citation metadata.

---

## 📬 Maintainers & Support

* **Engineering Team**: SevenWings Enterprise AI Architecture Group
* **Repository**: `Sevenwings26/AI-Content-Sentiment-Keywords-Gemini-powered`
