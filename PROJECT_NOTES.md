# 📓 SQLWhisperer — Project Ledger & Development Notes

> **Central Knowledge Log**: Tracks history, architectural decisions, current status, completed work, and upcoming open-source milestones.
> Managed manually and via `python -m scripts.project_tracker`.

---

## 🧭 Executive Summary

**SQLWhisperer** converts natural language questions into production-grade SQL with an automated self-healing loop, result inspection, few-shot feedback learning, and safety guardrails.

* **Tech Stack**: LangChain LCEL, FastAPI, Streamlit, PostgreSQL / SQLite, ChromaDB, SQLAlchemy, Pydantic v2.
* **Current Status**: **Phase 1-4 Complete** (Core engine, API, UI, memory, and tests fully implemented).
* **Next Mission**: Open-source transformation (Zero-setup demo, multi-dialect support, local LLMs, AST security, and packaging).

---

## 📜 Complete History & Completed Work

### Milestone 1: Core LangChain LCEL Chains (Completed)
- [x] **Schema Retriever** ([`src/chains/schema_retriever.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/schema_retriever.py)): Two-stage retrieval using LLM table selection followed by SQLAlchemy DDL inspection.
- [x] **Text2SQL Chain** ([`src/chains/text2sql.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/text2sql.py)): Generates dialect-aware SQL incorporating schema context and few-shot vector search examples.
- [x] **Validation Chain** ([`src/chains/validator.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/validator.py)): Structured output validator inspecting SQL syntax, table/column hallucination, and destructive commands. Auto-generates fixes for detected errors.
- [x] **Execution Chain** ([`src/chains/executor.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/executor.py)): Safe database executor with strict regex blocklist, row-count limits (`MAX_RESULT_ROWS`), and execution timing.
- [x] **Result Inspector Chain** ([`src/chains/inspector.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/inspector.py)): Evaluates whether returned data actually answers the user's question or looks suspicious/empty.
- [x] **Explanation Chain** ([`src/chains/explainer.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/explainer.py)): Produces plain-English executive summaries of the query results and business logic.
- [x] **Self-Healing Pipeline Orchestrator** ([`src/chains/pipeline.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/pipeline.py)): Iterative feedback loop (up to 3 retries) coordinating all chains on error.

### Milestone 2: Memory & Feedback Loop (Completed)
- [x] **ChromaDB Few-Shot Vector Store** ([`src/memory/few_shot_store.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/memory/few_shot_store.py)): Semantic search for similar question-SQL pairs using OpenAI embeddings.
- [x] **Feedback Learning Handler** ([`src/memory/feedback.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/memory/feedback.py)): When users approve a query (thumbs up), it's automatically embedded into ChromaDB to improve future runs.
- [x] **Few-Shot Seeding Script** ([`scripts/seed_few_shots.py`](file:///c:/Users/admin/Desktop/Sql_bot/scripts/seed_few_shots.py)): 10 curated baseline query pairs covering JOINs, aggregations, date filters, subqueries, and CASE statements.

### Milestone 3: Database & Persistence Layer (Completed)
- [x] **Target DB Connector** ([`src/db/connector.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/db/connector.py)): Native SQLAlchemy inspector extracting column types, PKs, FKs, and live sample rows.
- [x] **Query History DB** ([`src/db/history.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/db/history.py), [`src/db/models.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/db/models.py)): SQLite audit store logging every query, execution time, self-healing retries, result row counts, and user feedback.
- [x] **E-Commerce Demo Schema** ([`scripts/init_db.sql`](file:///c:/Users/admin/Desktop/Sql_bot/scripts/init_db.sql)): PostgreSQL schema with `customers`, `products`, `orders`, and `order_items` with realistic indexes.
- [x] **Synthetic Data Generator** ([`scripts/seed_db.py`](file:///c:/Users/admin/Desktop/Sql_bot/scripts/seed_db.py)): Generates 500 customers, 100 products, and 2,000 orders with realistic status distributions.

### Milestone 4: Presentation & API Layer (Completed)
- [x] **FastAPI Service** ([`src/api/app.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/api/app.py), [`src/api/routes.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/api/routes.py)): RESTful endpoints (`/api/v1/query`, `/api/v1/feedback`, `/api/v1/history`, `/api/v1/health`) with CORS and OpenAPI docs.
- [x] **Pydantic Schemas** ([`src/schemas/request.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/schemas/request.py), [`src/schemas/response.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/schemas/response.py)): Strict request validation and typed responses.
- [x] **Streamlit Chat UI** ([`streamlit_app/app.py`](file:///c:/Users/admin/Desktop/Sql_bot/streamlit_app/app.py)): Dark modern UI with metric cards, syntax-highlighted SQL, interactive data tables, plain-English summaries, and thumbs up/down feedback.
- [x] **Docker Support** ([`docker-compose.yml`](file:///c:/Users/admin/Desktop/Sql_bot/docker-compose.yml), [`Dockerfile.api`](file:///c:/Users/admin/Desktop/Sql_bot/Dockerfile.api), [`Dockerfile.streamlit`](file:///c:/Users/admin/Desktop/Sql_bot/Dockerfile.streamlit)): Multi-container stack with non-root security.
- [x] **Windows Automation** ([`run.bat`](file:///c:/Users/admin/Desktop/Sql_bot/run.bat), [`stop.bat`](file:///c:/Users/admin/Desktop/Sql_bot/stop.bat)): One-click startup and teardown scripts.

### Milestone 5: Testing & Reliability (Completed)
- [x] Unit tests for SQL execution safety regex guardrails ([`tests/test_chains/test_executor.py`](file:///c:/Users/admin/Desktop/Sql_bot/tests/test_chains/test_executor.py)).
- [x] Unit tests for structured validator models ([`tests/test_chains/test_validator.py`](file:///c:/Users/admin/Desktop/Sql_bot/tests/test_chains/test_validator.py)).
- [x] Integration tests for query history SQLite database ([`tests/test_chains/test_pipeline.py`](file:///c:/Users/admin/Desktop/Sql_bot/tests/test_chains/test_pipeline.py)).
- [x] Integration tests for API routes, feedback normalization, and isolation ([`tests/test_api/test_routes.py`](file:///c:/Users/admin/Desktop/Sql_bot/tests/test_api/test_routes.py)).

### Milestone 6: Enterprise Production-Grade Transformation (Completed)
- [x] **Zero-Trust AST Sandbox** ([`src/security/sandbox.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/security/sandbox.py)): Strict `sqlglot` parse tree validator blocking write CTEs, multiple statements, catalog exfiltration, and restricted system functions.
- [x] **Database Session Sandboxing** ([`src/security/sandbox.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/security/sandbox.py)): Storage-engine read-only transaction enforcement (`SET TRANSACTION READ ONLY` / `PRAGMA query_only = ON`) and query execution timeouts.
- [x] **Data Loss Prevention (DLP) Redaction** ([`src/security/redactor.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/security/redactor.py)): In-flight PII masking (emails, SSNs, credit cards, phone numbers, sensitive columns) before sending to LLM context or user preview.
- [x] **Sliding-Window Rate Limiting** ([`src/api/rate_limiter.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/api/rate_limiter.py)): Middleware throttling requests per client to protect LLM token quotas.
- [x] **Real-Time SSE Streaming** ([`src/chains/pipeline.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/pipeline.py), [`src/api/routes.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/api/routes.py)): Live pipeline stage streaming via `/api/v1/query/stream` Server-Sent Events.
- [x] **Multi-Tier Semantic Caching** ([`src/memory/semantic_cache.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/memory/semantic_cache.py)): Exact hash and semantic vector caching for sub-50ms repeat query responses.
- [x] **Multi-Provider Fallback Cascade** ([`src/chains/llm_factory.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/llm_factory.py)): Automatic failover cascade (Groq ➜ Gemini ➜ OpenAI ➜ Ollama) using LangChain `.with_fallbacks()`.
- [x] **Golden Evaluation Benchmark Harness** ([`tests/eval/`](file:///c:/Users/admin/Desktop/Sql_bot/tests/eval/)): Standardized test suite measuring Valid SQL Rate (VSR) and Execution Accuracy (EX) in CI.
- [x] **Production Multi-Stage Docker Build** ([`Dockerfile.api`](file:///c:/Users/admin/Desktop/Sql_bot/Dockerfile.api)): Hardened builder/runtime stages with non-root security and container healthchecks.
- [x] **Test Suite**: 57/57 unit, integration, offensive security, and benchmark tests passing.

---

## 🎯 Current Work (Completed)

* Enterprise production-grade architecture fully deployed and verified across 57 automated tests.

## 🚀 Open-Source Transformation Roadmap

### Phase 1: Open-Source Governance & Community Files
- [x] Add `LICENSE` (MIT).
- [x] Create `pyproject.toml` (PEP 621 packaging & dev tools).
- [x] Create `CONTRIBUTING.md` (development instructions, standards, PR workflow).
- [x] Create `CODE_OF_CONDUCT.md` (Contributor Covenant).
- [x] Create `SECURITY.md` (responsible disclosure policy).
- [x] Create GitHub issue and pull request templates (`.github/ISSUE_TEMPLATE/`).
- [x] Create GitHub Actions CI workflow (`.github/workflows/ci.yml`).

### Phase 2: Zero-Friction Demo Mode & Multi-Dialect
- [x] Create auto-generating SQLite demo DB so users can run without PostgreSQL ([`scripts/seed_sqlite.py`](file:///c:/Users/admin/Desktop/Sql_bot/scripts/seed_sqlite.py)).
- [x] Automatic database fallback in [`src/db/connector.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/db/connector.py).
- [x] Abstract dialect formatting dynamically (`get_dialect_name()`).

### Phase 3: Pluggable LLMs (Local & Cloud)
- [x] Add LLM Provider Factory ([`src/chains/llm_factory.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/llm_factory.py)) supporting Ollama local models and OpenAI.
- [x] Migrate all chains (`schema_retriever`, `text2sql`, `validator`, `inspector`, `explainer`) to `get_chat_llm()`.

### Phase 4: AST-Level Security Hardening
- [x] Integrate `sqlglot` for deterministic AST inspection in [`src/chains/executor.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/chains/executor.py).
- [x] Unit test suite covering AST validation & mutation intercept ([`tests/test_chains/test_executor.py`](file:///c:/Users/admin/Desktop/Sql_bot/tests/test_chains/test_executor.py)).

### Phase 5: Semantic Business Layer
- [x] Add [`config/glossary.yaml`](file:///c:/Users/admin/Desktop/Sql_bot/config/glossary.yaml) for domain metrics ("active customer", "revenue", "churn") and rules.
- [x] Contextual matching engine in [`src/semantic/glossary.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/semantic/glossary.py) with unit tests ([`tests/test_semantic.py`](file:///c:/Users/admin/Desktop/Sql_bot/tests/test_semantic.py)).

### Phase 6: Packaging, CLI & Analytics UX
- [x] Standard `pyproject.toml` with `sqlwhisperer` entrypoint.
- [x] Terminal CLI with `query` and `health` commands ([`src/cli/main.py`](file:///c:/Users/admin/Desktop/Sql_bot/src/cli/main.py)).
- [x] Auto-charting (Bar, Line, Area) and 1-click CSV export in Streamlit UI ([`streamlit_app/app.py`](file:///c:/Users/admin/Desktop/Sql_bot/streamlit_app/app.py)).
- [x] GitHub Actions workflow ([`.github/workflows/ci.yml`](file:///c:/Users/admin/Desktop/Sql_bot/.github/workflows/ci.yml)).

---

## 📝 Activity & Development Log

| Timestamp | Event / Action | Status | Notes |
| :--- | :--- | :--- | :--- |
| 2026-10-02 17:49 | Free LLMs Added | Completed | Added 100% Free AI Providers: Groq (Llama 3.3 70B, Qwen 2.5 Coder), Google Gemini (Gemini 2.0 Flash free tier), Ollama (local offline), and OpenRouter with in-browser switcher |
| 2026-10-02 17:06 | Bugfix | Completed | Fixed LangChain 0.3+ import (langchain_core.documents) in FewShotStore and verified API health, DB test, and Schema explorer endpoints |
| 2026-10-02 16:30 | UI Overhaul | Completed | Streamlit UX overhaul: Direct DB URL input, SQLite file drag-and-drop upload, Interactive Schema Explorer with column details and sample rows, and in-browser API key manager |
| 2026-10-02 16:21 | Phase 5 & 6 Done | Completed | Phase 5 & 6 Complete: Semantic Layer (glossary.yaml), CLI tool (sqlwhisperer query/health), and Streamlit auto-charting with CSV export |
| 2026-10-02 16:09 | Phase 4 Done | Completed | Phase 4 Complete: AST-level SQL validation with sqlglot, recursive mutation detection, and unit tests |
| 2026-10-02 16:08 | Phase 2 & 3 Done | Completed | Phase 2 & 3 Complete: Zero-setup SQLite demo mode, dialect awareness, and local LLM factory (Ollama/OpenAI) |
| 2026-10-02 15:51 | Phase 1 Done | Completed | Phase 1 Complete: LICENSE (MIT), pyproject.toml, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, and GitHub Actions CI workflow implemented |
| 2026-10-02 15:46 | Roadmap Planned | Completed | Initialized Open-Source Evolution Plan and project tracker script |
| Initial Setup | Full architecture & 41 files scaffolded | Completed | Chains, API, UI, Memory, Docker, Seeds |
| Tests Created | Offline unit tests & fixtures created | Completed | Guardrails, schemas, and history tests |
| Automation | `run.bat` and `stop.bat` implemented | Completed | One-click service orchestration |
| Open-Source Plan | Architecture review & open-source roadmap | Active | Devised zero-setup and multi-provider plan |
| Project Tracker | Created `scripts/project_tracker.py` & ledger | Active | Automated notes and health checking |
