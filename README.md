# 🔮 SQLWhisperer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Architecture: 80/20](https://img.shields.io/badge/Architecture-80%2F20%20Systems%20Engineering-blueviolet)](https://github.com/sqlwhisperer/sqlwhisperer)

**Autonomous Natural Language to Production SQL Engine with Self-Healing, Pure-AST Validation & High-End Auto-Visualization Studio.**

SQLWhisperer is an engineering-first analytics engine that converts natural language into production SQL, executes queries safely within an AST sandbox, validates database operations deterministically in `<1ms`, and automatically renders executive Plotly visualizations with instant data insights.

---

## ⚡ What Makes SQLWhisperer Stand Out?

Most Text-to-SQL projects are fragile API wrappers that dump raw schemas into prompts and crash on complex joins. SQLWhisperer takes an **80/20 systems engineering approach**:

- 🎨 **High-End Auto-Visualization Studio**: Automatically inspects query result shapes and renders publication-ready Plotly charts — from **KPI Scorecard Ribbons** and **Spline Area Trends** to **Hierarchical Treemaps**, **Conversion Funnels**, **2D Matrix Heatmaps**, **Choropleth Maps**, and **Outlier Box Plots**.
- 💡 **Automated Data Insights**: Generates executive highlights (top contributors, Pareto distribution concentration, and volatility ratios) directly alongside visual charts.
- ⚡ **Pure-AST Deterministic SQL Validator**: Uses `sqlglot` Abstract Syntax Trees to verify table/column existence, detect accidental Cartesian joins, and enforce ANSI `GROUP BY` rules in **`<1ms` consuming 0 LLM tokens**.
- 🕸️ **Foreign Key Graph Traversal (BFS)**: Mathematically computes shortest-path join bridges (e.g. `customers` $\to$ `orders` $\to$ `order_items` $\to$ `products`), guaranteeing junction tables are never omitted.
- 🛠️ **AST Query Optimizer**: Automatically injects safety `LIMIT` caps to prevent unbounded queries and normalizes dialect-specific functions (e.g., PostgreSQL `NOW()` $\to$ SQLite `DATETIME('now')`).
- 🧠 **100% Free & Offline Embeddings**: Runs ChromaDB few-shot learning on CPU with built-in ONNX `all-MiniLM-L6-v2` embeddings — zero paid OpenAI API key required.
- 🛡️ **Zero-Trust Security Sandbox**: Single-statement enforcement, strict AST read-only verification, and engine-level read-only transactions.

---

## 🏗️ Architecture

```
User Question
      │
      ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Context Retrieval (Parallel 0ms Fast-Path)                             │
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
                                     ▼
                      ┌─────────────────────────────┐
                      │  Auto-Visualization Studio  │ (Treemap, Heatmap, Funnel, Trend, KPI)
                      └─────────────────────────────┘
```

---

## 📊 Supported Visualizations

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

## 🚀 Quick Start (Under 60 Seconds)

### Option A: 1-Click Windows Launcher

Simply double-click `run.bat` or run:
```bat
run.bat
```
*(Automatically verifies dependencies, initializes the embedded SQLite e-commerce dataset, seeds local vector memory, and starts both FastAPI backend and Streamlit UI).*

---

### Option B: Manual Setup

1. **Clone & Install Dependencies**:
   ```bash
   git clone https://github.com/sqlwhisperer/sqlwhisperer.git
   cd sqlwhisperer
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   ```
   *Tip: SQLWhisperer works out of the box with **Groq** (100% free high-speed inference) or local **Ollama**.*

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

SQLWhisperer includes a comprehensive unit and integration test suite:
```bash
python -m pytest tests/
```
Tests cover:
- Pure-AST validation & security sandbox enforcement
- Foreign Key graph traversal & bridge connection
- Query rewriting & safety LIMIT injection
- Auto-visualization heuristic classification & Plotly rendering
- Business glossary matching & ChromaDB local embeddings

---

## 📄 License

Distributed under the [MIT License](LICENSE).
