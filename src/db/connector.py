"""Database connector utilities.

Provides schema introspection and connection management with automatic
zero-setup SQLite fallback when PostgreSQL is unavailable.

Engine instances are cached per database URL to avoid connection pool
thrashing.  Pass ``database_url`` overrides to functions instead of
mutating global settings.
"""

from __future__ import annotations

import threading
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from src.config.settings import settings
from loguru import logger

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DEFAULT_SQLITE_URL = f"sqlite:///{DATA_DIR / 'demo_ecommerce.db'}"

# ── Engine cache (thread-safe) ────────────────────────────────────
_engine_cache: dict[str, Engine] = {}
_schema_cache: dict[str, dict[str, Any]] = {}
_engine_lock = threading.Lock()


def _ensure_sqlite_demo_db():
    """Ensure the SQLite demo database exists and is seeded."""
    db_file = DATA_DIR / "demo_ecommerce.db"
    if not db_file.is_file() or db_file.stat().st_size == 0:
        logger.info("📦 SQLite demo database not found. Generating sample data...")
        from scripts.seed_sqlite import seed_sqlite
        seed_sqlite(db_file)


def get_engine(database_url: str | None = None) -> Engine:
    """Return a SQLAlchemy engine for the target database.

    Parameters
    ----------
    database_url:
        Override the database URL.  When ``None``, falls back to
        ``settings.database_url``.

    The engine is cached per URL so the connection pool is reused across
    calls.  If the configured database URL is unreachable (e.g. Postgres
    is not running), transparently falls back to the embedded SQLite demo DB.
    """
    db_url = (database_url or settings.database_url).strip()

    # Return cached engine if available
    with _engine_lock:
        if db_url in _engine_cache:
            return _engine_cache[db_url]

    # Check if configured directly for SQLite
    if db_url.startswith("sqlite"):
        _ensure_sqlite_demo_db()
        engine = create_engine(db_url, pool_pre_ping=True)
        with _engine_lock:
            _engine_cache[db_url] = engine
        return engine

    # Attempt to connect to configured DB (e.g. Postgres)
    try:
        connect_args = {"connect_timeout": 3} if "postgres" in db_url else {}
        engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        with _engine_lock:
            _engine_cache[db_url] = engine
        return engine
    except Exception as exc:
        logger.warning(
            f"⚠️ Could not connect to primary database ({db_url}): {exc}. "
            "Falling back to embedded SQLite demo database."
        )
        _ensure_sqlite_demo_db()
        engine = create_engine(DEFAULT_SQLITE_URL, pool_pre_ping=True)
        with _engine_lock:
            _engine_cache[DEFAULT_SQLITE_URL] = engine
        return engine


def invalidate_engine(database_url: str | None = None) -> None:
    """Remove a cached engine (e.g. when the user switches databases).

    If *database_url* is ``None``, clears the entire cache.
    """
    with _engine_lock:
        if database_url:
            engine = _engine_cache.pop(database_url, None)
            _schema_cache.pop(database_url, None)
            if engine:
                engine.dispose()
        else:
            for eng in _engine_cache.values():
                eng.dispose()
            _engine_cache.clear()
            _schema_cache.clear()


def get_dialect_name(database_url: str | None = None) -> str:
    """Return a normalized, human-readable dialect name for prompts."""
    engine = get_engine(database_url)
    dialect_name = engine.dialect.name.lower()

    mapping = {
        "sqlite": "SQLite",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "duckdb": "DuckDB",
        "snowflake": "Snowflake",
        "oracle": "Oracle",
        "mssql": "MSSQL",
    }
    return mapping.get(dialect_name, dialect_name.capitalize())


def get_table_names(database_url: str | None = None) -> list[str]:
    """Return all table names in the target database."""
    engine = get_engine(database_url)
    inspector = inspect(engine)
    return inspector.get_table_names()


def get_table_info(tables: list[str] | None = None, database_url: str | None = None) -> str:
    """Return DDL-like schema info + sample rows for the requested tables.

    If *tables* is ``None``, returns info for all tables.
    """
    engine = get_engine(database_url)
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()

    target_tables = tables if tables else all_tables
    target_tables = [t for t in target_tables if t in all_tables]

    lines: list[str] = []

    with engine.connect() as conn:
        for table_name in target_tables:
            columns = inspector.get_columns(table_name)
            pk = inspector.get_pk_constraint(table_name)
            fks = inspector.get_foreign_keys(table_name)

            # Build CREATE TABLE-like representation
            lines.append(f"\nCREATE TABLE {table_name} (")
            col_lines = []
            for col in columns:
                nullable = "" if col.get("nullable", True) else " NOT NULL"
                default = ""
                if col.get("default") is not None:
                    default = f" DEFAULT {col['default']}"
                col_lines.append(
                    f"  {col['name']} {col['type']}{nullable}{default}"
                )

            # Primary key
            if pk and pk.get("constrained_columns"):
                pk_cols = ", ".join(pk["constrained_columns"])
                col_lines.append(f"  PRIMARY KEY ({pk_cols})")

            # Foreign keys
            for fk in fks:
                src_cols = ", ".join(fk.get("constrained_columns", []))
                ref_table = fk.get("referred_table", "")
                ref_cols = ", ".join(fk.get("referred_columns", []))
                if src_cols and ref_table:
                    col_lines.append(
                        f"  FOREIGN KEY ({src_cols}) REFERENCES {ref_table}({ref_cols})"
                    )

            lines.append(",\n".join(col_lines))
            lines.append(");")

            # Sample rows (up to 3) — use quoted identifier
            try:
                result = conn.execute(
                    text(f'SELECT * FROM "{table_name}" LIMIT 3')
                )
                sample_rows = result.fetchall()
                col_names = list(result.keys())
                if sample_rows:
                    lines.append(f"\n/* Sample rows from {table_name}: */")
                    lines.append(f"/* Columns: {', '.join(col_names)} */")
                    for row in sample_rows:
                        lines.append(f"/* {row} */")
            except Exception:
                pass  # sample rows are optional

            lines.append("")

    return "\n".join(lines)


def get_schema_metadata(database_url: str | None = None) -> dict[str, dict[str, Any]]:
    """Return structured schema metadata (tables, column sets, PKs, FKs) with caching."""
    db_url = (database_url or settings.database_url).strip()

    with _engine_lock:
        if db_url in _schema_cache:
            return _schema_cache[db_url]

    engine = get_engine(database_url)
    inspector = inspect(engine)
    metadata: dict[str, dict[str, Any]] = {}

    for table_name in inspector.get_table_names():
        try:
            columns = inspector.get_columns(table_name)
            pk = inspector.get_pk_constraint(table_name)
            fks = inspector.get_foreign_keys(table_name)

            col_set = {col["name"].lower() for col in columns}
            pk_set = set(pk.get("constrained_columns", [])) if pk else set()
            fk_list = []
            for fk in fks:
                fk_list.append({
                    "constrained_columns": [c.lower() for c in fk.get("constrained_columns", [])],
                    "referred_table": (fk.get("referred_table") or "").lower(),
                    "referred_columns": [c.lower() for c in fk.get("referred_columns", [])],
                })

            metadata[table_name.lower()] = {
                "columns": col_set,
                "primary_keys": pk_set,
                "foreign_keys": fk_list,
            }
        except Exception as exc:
            logger.debug(f"Failed to inspect metadata for table {table_name}: {exc}")

    with _engine_lock:
        _schema_cache[db_url] = metadata

    return metadata
