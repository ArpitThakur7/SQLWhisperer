<div align="center">

# 🔮 SQLWhisperer

### Autonomous Natural Language to Production SQL Engine with Self-Healing, Pure-AST Validation & High-End Auto-Visualization Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Architecture: 80/20 Systems](https://img.shields.io/badge/Architecture-80%2F20%20Systems%20Engineering-blueviolet)](https://github.com/ArpitThakur7/SQLWhisperer)
[![Tests: 86 Passed](https://img.shields.io/badge/Tests-86%20Passed%20(100%25)-brightgreen)](https://github.com/ArpitThakur7/SQLWhisperer)

<br />

<p align="center">
  <img src="docs/images/hero_banner.jpg" alt="SQLWhisperer Auto-Visualization Studio Dashboard" width="95%" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.5);" />
</p>

</div>

---

## ⚡ What Makes SQLWhisperer Stand Out?

Most Text-to-SQL projects on GitHub are brittle 5-line wrappers that dump raw schemas into prompts and crash on complex joins. **SQLWhisperer takes an 80/20 systems engineering approach**:

* 📐 **Automatic Schema ERD Rendering**: Live interactive Graphviz topology mapping database tables, column types, primary keys (🔑), and foreign key link bridges (🔗) right inside the Web Studio.
* 🌐 **Multi-DB Federation (DuckDB)**: In-memory virtual engine executing cross-database joins across disjoint SQLite databases, PostgreSQL instances, and analytical files simultaneously.
* ⚡ **Distributed Redis Caching & Rate Limiting**: Multi-tier exact hash cache and Redis Sorted Set (ZSET) sliding-window rate limiter with sub-millisecond lookups, surviving server restarts and synchronizing across multiple API workers (with automatic, zero-overhead fallback to local in-memory caching when running without Redis).
* 🎨 **High-End Auto-Visualization Studio**: Automatically inspects query result shapes and renders publication-ready Plotly charts — from **KPI Scorecard Ribbons** and **Spline Area Trends** to **Hierarchical Treemaps**, **Conversion Funnels**, **2D Matrix Heatmaps**, **Choropleth Maps**, and **Outlier Box Plots**, complete with an interactive Studio Controls Toolbar for real-time chart type and axis overrides.
* 💡 **Automated Data Insights**: Directly generates executive analytical highlights (identifying top contributors, Pareto concentration risk, and volatility spread) alongside visual charts.
* ⚡ **Pure-AST Deterministic SQL Validator**: Uses `sqlglot` Abstract Syntax Trees to verify table/column existence against live catalogs, catch accidental Cartesian joins, and enforce ANSI `GROUP BY` rules in **`<1ms` consuming 0 LLM tokens**.
* 🕸️ **Foreign Key Graph Traversal (BFS)**: Mathematically computes shortest-path join bridges across database schemas (e.g., `customers` $\to$ `orders` $\to$ `order_items` $\to$ `products`), guaranteeing junction tables are never omitted.
* 🛠️ **AST Query Optimizer**: Automatically injects safety `LIMIT` caps to prevent unbounded queries and normalizes dialect-specific functions (e.g., PostgreSQL `NOW()` $\to$ SQLite `DATETIME('now')`).
* 🧠 **100% Free & Offline Embeddings**: Runs ChromaDB few-shot learning on CPU with built-in ONNX `all-MiniLM-L6-v2` embeddings — zero paid OpenAI API key required.
* 🛡️ **Zero-Trust Security Sandbox**: Single-statement enforcement, strict AST read-only verification, and engine-level read-only transactions.

## 🖥️ Live Studio & Interactive Workspace

SQLWhisperer provides a sleek, dark-mode Web Studio designed for business analysts, data teams, and engineers alike:

### 1. Natural Language to SQL & Live Schema Explorer
Ask questions in everyday English — SQLWhisperer handles complex multi-table joins, filters, and aggregations while letting you inspect your live database catalog in real time:

<p align="center">
  <img src="docs/images/streamlit_query_execution.png" alt="SQLWhisperer Live Query Execution with Schema Explorer and Metric Cards" width="95%" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.5);" />
</p>

* 🔌 **Dynamic Database Switcher**: Toggle seamlessly between the embedded demo SQLite dataset, custom PostgreSQL/MySQL connection strings, or drag-and-drop SQLite file uploads.
* 📂 **Live Schema Explorer**: Expand tables in the sidebar to inspect column types, primary keys, and real-time row counts without writing manual `PRAGMA` or `INFORMATION_SCHEMA` queries.
* ⚡ **Live Performance & Confidence Metrics**: Instant transparency into row counts, sub-millisecond execution times, confidence percentages, and self-healing retry counts.
* 🤖 **Multi-Provider AI Hot-Swapping**: Switch models across Groq (Llama 3.3 70B), Google Gemini (Gemini 2.0 Flash), local Ollama (100% offline), OpenRouter, and OpenAI directly from the sidebar.

### 2. Auto-Chart Studio & Key Analytical Highlights
The engine automatically detects the optimal visual representation for your query results and extracts executive highlights:

<p align="center">
  <img src="docs/images/streamlit_chart_studio.png" alt="SQLWhisperer Auto-Chart Studio with KPI Metric Ribbon and Key Analytical Highlights" width="95%" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.5);" />
</p>

* 📊 **Executive Metric Ribbons**: Aggregates sum totals ($\Sigma$), averages ($\mu$), peak values ($\uparrow$), and total rows analyzed ($N$) at a glance.
* 📈 **Interactive Plotly Visualizations**: Hover inspection, zoom, pan, and direct image export with high-contrast themes.
* 🛠️ **Studio Controls Toolbar**: Override chart formats (Bar, Line, Area, Treemap, Funnel, Heatmap, Box Plot) and remap X/Y axes in real time.
* 💡 **Automated Data Insights**: Instant narrative callouts identifying top contributors, Pareto concentration shares, and growth anomalies.

---

## 📊 Visual Studio Multi-Format Matrix

<p align="center">
  <img src="docs/images/visualizer_showcase.jpg" alt="SQLWhisperer Multi-Format Visualization Studio" width="95%" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.5);" />
</p>

| Visual Format | Best Used For | Interactive Studio Features |
| :--- | :--- | :--- |
| **KPI Scorecard Ribbon** | Single aggregated KPIs & metrics | Value formatting, percentage delta comparisons |
| **Hierarchical Treemap** | Multi-level category & volume breakdowns | Color-scaled nested rectangles, zoomable levels |
| **2D Density Heatmap** | Cross-tabulated categorical matrices | Continuous contrast scale, density labels |
| **Stage Funnel** | Lifecycle pipelines & conversion dropoffs | Stage progression percentages, custom connectors |
| **Geographic Choropleth** | Country & regional distribution | Global land contours, interactive country hover |
| **Spline Area & Multi-Line** | Temporal trends & growth over time | Automatic peak annotations, rolling moving averages |
| **Donut with Center Stats** | Discrete categorical composition (<7 slices) | Hole percentage metrics, hover slice shares |
| **Ranked Horizontal Bar** | Entity rankings & leaderboards | Auto-sorted values, direct numeric badges |
| **Distribution Box Plot** | Value spread & statistical outlier detection | Quartile whiskers, outlier point plotting |

---

## 🏗️ Architecture

```
User Question
      │
      ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Distributed Rate Limiter & Multi-Tier Caching (0ms Fast-Path)          │
│ ├─ Redis ZSET Sliding-Window Limiter (with in-memory fallback)         │
│ ├─ Redis Tier 1A Exact Query Cache (with in-memory Tier 1B fallback)  │
│ └─ Redis Schema Metadata Cache (30-min TTL DB catalog introspection)   │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ (On Cache Miss)
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Context Retrieval & Memory                                             │
│ ├─ FK Graph Traversal (BFS shortest-path table bridge discovery)       │
│ ├─ Semantic Business Glossary (Vocabulary & metric rule expansion)     │
│ └─ ChromaDB Vector Memory (Local ONNX all-MiniLM-L6-v2 embeddings)     │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │  Text2SQL Generation Engine │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │  AST Optimizer & Rewriter   │ (Safety LIMIT, date normalization)
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │  Pure-AST Compiler Check    │ (<1ms, 0 tokens, live schema check)
                      └──────────────┬──────────────┘
                                     │ (On error: Self-Healing retry loop)
                                     ▼
                      ┌─────────────────────────────┐
                      │  Sandboxed DB Execution     │ (Read-only transaction, timeout guard)
                      └──────────────┬──────────────┘
                                     │
             ┌───────────────────────┴───────────────────────┐
             ▼                                               ▼
┌─────────────────────────────┐               ┌─────────────────────────────┐
│  Auto-Visualization Studio  │               │ DuckDB Multi-DB Federation  │
│  (Treemap, Funnel, Heatmap) │               │ (Cross-database virtual OLAP│
└────────────┬────────────────┘               └─────────────────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Schema ERD Visualizer      │ (Graphviz DOT topology with PKs & FK bridges)
└─────────────────────────────┘
```

> 📖 **Deep Dive**: For full sequence diagrams, state machines, and ADRs, see the comprehensive [ARCHITECTURE.md](ARCHITECTURE.md) blueprint and interactive [architecture_visualizer.html](architecture_visualizer.html).

---

## 🔌 Decoupled Backend & Interactive API

SQLWhisperer features a high-performance **FastAPI** backend supporting both standard synchronous JSON requests and **Server-Sent Events (SSE)** for real-time progress streaming:

<p align="center">
  <img src="docs/images/fastapi_docs.png" alt="FastAPI Interactive OpenAPI Documentation" width="48%" style="border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); margin-right: 10px;" />
  <img src="docs/images/fastapi_response.png" alt="FastAPI Live Health & Diagnostics Response" width="48%" style="border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);" />
</p>

- `POST /api/v1/query`: Core natural language query endpoint with Redis/in-memory multi-tier caching.
- `POST /api/v1/query/stream`: Real-time Server-Sent Events (SSE) streaming with stage diagnostics.
- `GET /api/v1/health`: Live system health, engine dialect, Redis status, and active LLM provider.
- `GET /api/v1/history`: Persisted query history with latency and confidence metrics.
- `POST /api/v1/db/test`: Database connection tester and schema inspector.
- `GET /api/v1/db/schema`: Column DDL reflection, primary key flags, and 3-row data previews.
- `GET /api/v1/db/erd`: Dynamic Graphviz DOT schema topology and foreign-key link visualizer.
- `GET /api/v1/federation/catalogs`: List all attached database catalogs in the DuckDB virtual engine.
- `POST /api/v1/federation/query`: Cross-database federated SQL querying across multiple attached databases.

---

## 🚀 Quick Start (Under 60 Seconds)

### Option A: 1-Click Windows Launcher

Simply double-click `run.bat` or run:
```bat
run.bat
```
*(Automatically verifies dependencies, initializes the embedded SQLite e-commerce dataset, seeds local vector memory, and starts both FastAPI backend and Streamlit UI).*

---

### Option B: Docker Compose (Full Stack with PostgreSQL & Redis)

Launch the complete microservice stack (PostgreSQL, Redis 7, FastAPI, and Streamlit) with a single command:
```bash
docker compose up --build
```

---

### Option C: Manual Setup

1. **Clone & Install Dependencies**:
   ```bash
   git clone https://github.com/ArpitThakur7/SQLWhisperer.git
   cd sqlwhisperer
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   ```
   *Tip: SQLWhisperer works out of the box with **Groq** (100% free high-speed cloud inference) or local **Ollama**.*

3. **Start Services**:
   ```bash
   # Terminal 1: FastAPI Backend
   python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

   # Terminal 2: Streamlit Studio UI
   python -m streamlit run streamlit_app/app.py
   ```

Then open:
- **Streamlit Web Studio**: [http://localhost:8501](http://localhost:8501)
- **FastAPI OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Testing

SQLWhisperer includes a comprehensive unit and integration test suite (**86/86 tests passing**):
```bash
python -m pytest tests/
```
Tests cover:
- Automatic Schema ERD generation (Graphviz DOT syntax, PK/FK links)
- Multi-DB Federation engine queries via in-memory DuckDB
- Distributed Redis caching, TTL expiration, and graceful in-memory fallback
- Redis ZSET sliding-window rate limiting & multi-client isolation
- Pure-AST validation & security sandbox enforcement
- Foreign Key graph traversal & bridge connection
- Query rewriting & safety LIMIT injection
- Auto-visualization heuristic classification & Plotly rendering
- Business glossary matching & ChromaDB local embeddings

---

## 📄 License

Distributed under the [MIT License](LICENSE).
