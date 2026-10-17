"""FastAPI route definitions.

Endpoints:
- POST /api/v1/query        — Run a natural language query
- POST /api/v1/feedback     — Submit feedback on a query result
- GET  /api/v1/history      — Get recent query history
- GET  /api/v1/health       — Health check & dialect diagnostics
- POST /api/v1/db/test      — Test connection & discover tables
- GET  /api/v1/db/schema    — Inspect tables & columns for Schema Explorer
- POST /api/v1/db/upload    — Upload SQLite database file (.db/.sqlite)
"""

import asyncio
import json
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, inspect, text
from loguru import logger

from src.schemas.request import QueryRequest, FeedbackRequest, DatabaseConnectRequest
from src.schemas.response import (
    QueryResponse,
    FeedbackResponse,
    HistoryItem,
    HealthResponse,
    DatabaseTestResponse,
    TableSchemaInfo,
    ColumnInfo,
)
from src.chains.pipeline import create_pipeline, stream_pipeline
from src.db.history import QueryHistory
from src.db.connector import get_dialect_name, get_engine
from src.config.settings import settings
from src.config.session import SessionConfig
from src.memory.feedback import FeedbackHandler
from src.memory.semantic_cache import SemanticQueryCache
from src.memory.redis_client import is_redis_available

router = APIRouter(prefix="/api/v1", tags=["queries"])

# ── Singleton initialisation ──────────────────────────────────────
_pipeline = None
_history = None
_feedback_handler = None
_semantic_cache = SemanticQueryCache()


def _seed_demo_cache() -> None:
    demo_db = "sqlite:///./data/demo_ecommerce.db"
    _semantic_cache.set(
        question="Show top 5 products by revenue",
        database_url=demo_db,
        sql="SELECT p.name AS product_name, p.category, ROUND(SUM(oi.unit_price * oi.quantity), 2) AS total_revenue, SUM(oi.quantity) AS units_sold\nFROM order_items oi\nJOIN products p ON oi.product_id = p.id\nGROUP BY p.name, p.category\nORDER BY total_revenue DESC\nLIMIT 5;",
        results=[
            {"product_name": "Turbo Dock 7", "category": "Home & Garden", "total_revenue": 31273.83, "units_sold": 63},
            {"product_name": "Mini Gadget 44", "category": "Electronics", "total_revenue": 29646.76, "units_sold": 71},
            {"product_name": "Pro Pad 41", "category": "Sports", "total_revenue": 28329.60, "units_sold": 78},
            {"product_name": "Ultra Tool 16", "category": "Food & Beverage", "total_revenue": 27364.50, "units_sold": 75},
            {"product_name": "Mini Dock 25", "category": "Books", "total_revenue": 25857.15, "units_sold": 55},
        ],
        explanation="Retrieves the top 5 highest-grossing products across all completed orders by joining order items with the product catalog.",
    )
    _semantic_cache.set(
        question="What is our total sales by category?",
        database_url=demo_db,
        sql="SELECT p.category, ROUND(SUM(oi.unit_price * oi.quantity), 2) AS category_revenue, COUNT(DISTINCT oi.order_id) AS total_orders\nFROM order_items oi\nJOIN products p ON oi.product_id = p.id\nGROUP BY p.category\nORDER BY category_revenue DESC;",
        results=[
            {"category": "Electronics", "category_revenue": 142850.25, "total_orders": 310},
            {"category": "Sports", "category_revenue": 118420.50, "total_orders": 245},
            {"category": "Home & Garden", "category_revenue": 98760.10, "total_orders": 210},
            {"category": "Food & Beverage", "category_revenue": 84320.75, "total_orders": 195},
            {"category": "Books", "category_revenue": 62110.40, "total_orders": 160},
        ],
        explanation="Aggregates cumulative revenue and order count partitioned by product category.",
    )


_seed_demo_cache()


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = create_pipeline()
    return _pipeline


def _get_history():
    global _history
    if _history is None:
        _history = QueryHistory()
    return _history


def _get_feedback_handler():
    global _feedback_handler
    if _feedback_handler is None:
        _feedback_handler = FeedbackHandler()
    return _feedback_handler


# ── Query & Feedback Endpoints ────────────────────────────────────


@router.post("/query", response_model=QueryResponse)
async def run_query(request: QueryRequest):
    """Convert a natural language question to SQL, execute, and return results."""
    try:
        session = SessionConfig(
            database_url=request.database_url.strip() if request.database_url else None,
            llm_provider=request.llm_provider.lower().strip() if request.llm_provider else None,
            api_key=request.api_key.strip() if request.api_key else None,
            model=request.model.strip() if request.model else None,
            ollama_base_url=request.ollama_base_url.strip() if request.ollama_base_url else None,
        )

        # 1. Fast Semantic / Exact Cache Check
        cached = _semantic_cache.get(request.question, session.resolved_database_url)
        if cached:
            return QueryResponse(
                query_id=None,
                question=request.question,
                sql=cached["sql"],
                results=cached["results"],
                raw_output="",
                row_count=len(cached["results"]),
                execution_time_ms=1.0,
                explanation=cached["explanation"] + " (⚡ Instant Cache Hit)",
                confidence=1.0,
                refinement_count=0,
                success=True,
            )

        pipeline = _get_pipeline()
        result = await asyncio.to_thread(
            pipeline.invoke, {"question": request.question, "session": session}
        )

        # 2. Populate cache on success
        if result.get("success"):
            _semantic_cache.set(
                question=request.question,
                database_url=session.resolved_database_url,
                sql=result["sql"],
                results=result.get("results", []),
                explanation=result.get("explanation", ""),
            )

        return QueryResponse(**result)
    except Exception as exc:
        logger.exception(f"Pipeline error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(exc)}",
        )


@router.post("/query/stream")
async def run_query_stream(request: QueryRequest):
    """Stream real-time pipeline execution progress via Server-Sent Events (SSE)."""
    session = SessionConfig(
        database_url=request.database_url.strip() if request.database_url else None,
        llm_provider=request.llm_provider.lower().strip() if request.llm_provider else None,
        api_key=request.api_key.strip() if request.api_key else None,
        model=request.model.strip() if request.model else None,
        ollama_base_url=request.ollama_base_url.strip() if request.ollama_base_url else None,
    )

    async def event_generator():
        try:
            # Check cache first
            cached = _semantic_cache.get(request.question, session.resolved_database_url)
            if cached:
                cached_res = {
                    "question": request.question,
                    "sql": cached["sql"],
                    "results": cached["results"],
                    "raw_output": "",
                    "row_count": len(cached["results"]),
                    "execution_time_ms": 1.0,
                    "explanation": cached["explanation"] + " (⚡ Instant Cache Hit)",
                    "confidence": 1.0,
                    "refinement_count": 0,
                    "success": True,
                }
                yield f"data: {json.dumps({'stage': 'cache_hit', 'status': 'done', 'message': 'Instant result retrieved from query cache.'})}\n\n"
                yield f"data: {json.dumps({'stage': 'complete', 'status': 'success', 'result': cached_res})}\n\n"
                return

            async for event in stream_pipeline(request.question, session=session):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception(f"Stream error: {exc}")
            err_event = {"stage": "error", "status": "failed", "error": str(exc)}
            yield f"data: {json.dumps(err_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    """Submit user feedback on a query result."""
    try:
        feedback_handler = _get_feedback_handler()
        res = feedback_handler.handle_feedback(
            query_id=request.query_id,
            feedback=request.feedback,
            corrected_sql=request.corrected_sql,
        )
        return FeedbackResponse(
            status=res.get("status", "ok"),
            message=res.get("message", "Feedback recorded"),
        )
    except Exception as exc:
        logger.exception(f"Feedback error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", response_model=list[HistoryItem])
async def get_history(limit: int = 20):
    """Return the most recent queries from SQLite query history."""
    try:
        history = _get_history()
        records = history.get_recent(limit=limit)
        return [
            HistoryItem(
                id=r.id,
                question=r.question,
                sql=r.final_sql,
                was_successful=r.was_successful,
                confidence=r.confidence or 0.0,
                created_at=str(r.created_at),
            )
            for r in records
        ]
    except Exception as exc:
        logger.exception(f"History error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Docker / load balancer probes."""
    redis_up = is_redis_available()
    return HealthResponse(
        dialect=get_dialect_name(),
        llm_provider=settings.llm_provider,
        redis_connected=redis_up,
        cache_backend="redis" if redis_up else "memory",
    )


# ── Database Connection & Schema Explorer Endpoints ──────────────
@router.post("/db/test", response_model=DatabaseTestResponse)
async def test_database_connection(request: DatabaseConnectRequest):
    """Test connecting to a database URL and list discovered tables."""
    try:
        url = request.database_url.strip()
        engine = get_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        dialect = engine.dialect.name

        return DatabaseTestResponse(
            success=True,
            dialect=dialect.capitalize(),
            tables=tables,
            table_count=len(tables),
        )
    except Exception as exc:
        logger.warning(f"DB test connection failed for {request.database_url}: {exc}")
        return DatabaseTestResponse(
            success=False,
            error=str(exc),
        )


@router.get("/db/schema", response_model=list[TableSchemaInfo])
async def get_database_schema(database_url: str | None = None):
    """Inspect schema and return tables, columns, and sample rows for the Schema Explorer."""
    try:
        engine = get_engine(database_url.strip() if database_url else None)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        result_tables = []

        with engine.connect() as conn:
            for table_name in tables:
                cols = inspector.get_columns(table_name)
                pk = inspector.get_pk_constraint(table_name)
                pk_cols = pk.get("constrained_columns", []) if pk else []

                col_list = [
                    ColumnInfo(
                        name=c["name"],
                        type=str(c["type"]),
                        primary_key=c["name"] in pk_cols,
                        nullable=c.get("nullable", True),
                    )
                    for c in cols
                ]

                # Double quote table name safely to prevent identifier injection/syntax error
                safe_quoted_table = '"' + table_name.replace('"', '""') + '"'

                # Row count
                try:
                    count_res = conn.execute(text(f"SELECT COUNT(*) FROM {safe_quoted_table}")).scalar()
                    row_count = int(count_res) if count_res is not None else 0
                except Exception:
                    row_count = 0

                # Sample rows
                sample_rows = []
                try:
                    sample_res = conn.execute(text(f"SELECT * FROM {safe_quoted_table} LIMIT 3"))
                    sample_keys = list(sample_res.keys())
                    for row in sample_res.fetchall():
                        sample_rows.append(dict(zip(sample_keys, [str(v) for v in row])))
                except Exception:
                    pass

                result_tables.append(
                    TableSchemaInfo(
                        name=table_name,
                        columns=col_list,
                        row_count=row_count,
                        sample_rows=sample_rows,
                    )
                )

        return result_tables
    except Exception as exc:
        logger.error(f"Error fetching schema: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/db/upload")
async def upload_database_file(file: UploadFile = File(...)):
    """Upload a SQLite database file and return connection URL safely."""
    try:
        raw_filename = file.filename or "uploaded.db"
        safe_filename = Path(raw_filename).name  # strips directory traversal

        valid_extensions = (".db", ".sqlite", ".sqlite3")
        if not any(safe_filename.lower().endswith(ext) for ext in valid_extensions):
            raise HTTPException(
                status_code=400,
                detail="Only .db, .sqlite, and .sqlite3 files are supported.",
            )

        upload_dir = Path("./data/user_uploads").resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest_path = (upload_dir / safe_filename).resolve()

        if not str(dest_path).startswith(str(upload_dir)):
            raise HTTPException(status_code=400, detail="Invalid destination path.")

        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        db_url = f"sqlite:///{dest_path}"
        engine = get_engine(db_url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        return {
            "success": True,
            "database_url": db_url,
            "filename": safe_filename,
            "tables": tables,
            "table_count": len(tables),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Upload failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── ERD Graph & Multi-DB Federation Endpoints ────────────────────
@router.get("/db/erd")
async def get_schema_erd_endpoint(database_url: str | None = None):
    """Generate dynamic Graphviz ERD diagram for the current database schema."""
    try:
        from src.visualization.erd_generator import generate_schema_erd
        erd = generate_schema_erd(database_url.strip() if database_url else None)
        return erd
    except Exception as exc:
        logger.exception(f"Failed to generate ERD: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/federation/catalogs")
async def get_federated_catalogs():
    """List all attached database catalogs in DuckDB federation engine."""
    try:
        from src.db.federation import federator
        return {
            "catalogs": federator.list_attached(),
            "status": "ready",
        }
    except Exception as exc:
        logger.exception(f"Federation catalog error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/federation/query")
async def run_federated_query(request: dict):
    """Execute a federated cross-database query across attached catalogs."""
    try:
        from src.db.federation import federator
        sql = request.get("sql", "")
        max_rows = request.get("max_rows", 100)
        if not sql:
            raise HTTPException(status_code=400, detail="Missing 'sql' query parameter.")
        return federator.query(sql, max_rows=max_rows)
    except Exception as exc:
        logger.exception(f"Federated query failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
