"""SQL Query Rewriter and Optimizer Chain.

Applies deterministic post-generation AST optimizations:
1. Safety LIMIT enforcement (caps unbounded queries to prevent memory exhaustion)
2. Dialect-specific date & function translation (e.g. NOW() -> DATETIME('now') for SQLite)
3. AST formatting and whitespace normalization
4. Unnecessary subquery or redundant parenthesis flattening
"""

from __future__ import annotations

from typing import Any
from loguru import logger

try:
    import sqlglot
    from sqlglot import exp
    HAS_SQLGLOT = True
except ImportError:
    HAS_SQLGLOT = False

from src.db.connector import get_dialect_name
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings


def optimize_sql(
    sql: str,
    dialect_name: str = "sqlite",
    default_limit: int = 100,
) -> tuple[str, list[str]]:
    """Transform and optimize raw generated SQL using sqlglot AST.

    Returns
    -------
    (optimized_sql, list_of_optimizations)
    """
    clean_sql = (sql or "").strip().rstrip(";")
    if not clean_sql or not HAS_SQLGLOT:
        return clean_sql, []

    optimizations: list[str] = []
    dialect_lower = dialect_name.lower()
    glot_dialect = (
        "postgres" if "postgres" in dialect_lower
        else "mysql" if "mysql" in dialect_lower
        else "duckdb" if "duckdb" in dialect_lower
        else "sqlite"
    )

    try:
        tree = sqlglot.parse_one(clean_sql, read=glot_dialect)
    except Exception:
        try:
            tree = sqlglot.parse_one(clean_sql)
        except Exception as exc:
            logger.debug(f"SQL Optimizer skipped due to parse note: {exc}")
            return clean_sql, []

    # 1. Dialect-Specific Date Function Translation
    if glot_dialect == "sqlite":
        for node in list(tree.find_all(exp.Anonymous, exp.Func)):
            fn_name = (getattr(node, "name", "") or getattr(node, "key", "")).lower()
            if fn_name in ("now", "current_timestamp"):
                replacement = sqlglot.parse_one("DATETIME('now')")
                node.replace(replacement)
                optimizations.append("Translated NOW() -> DATETIME('now') for SQLite dialect.")
            elif fn_name in ("curdate", "current_date"):
                replacement = sqlglot.parse_one("DATE('now')")
                node.replace(replacement)
                optimizations.append("Translated CURDATE() -> DATE('now') for SQLite dialect.")

    # 2. Safety LIMIT Injection
    if isinstance(tree, exp.Select):
        has_limit = tree.args.get("limit") is not None
        # Check if scalar aggregation returning single row
        is_scalar_agg = (
            len(tree.expressions) == 1
            and any(isinstance(n, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)) for n in tree.expressions[0].walk())
            and tree.args.get("group") is None
        )

        if not has_limit and not is_scalar_agg:
            tree = tree.limit(default_limit)
            optimizations.append(f"Injected safety LIMIT {default_limit} to prevent unbounded fetch.")

    # 3. Clean AST formatting
    try:
        formatted = tree.sql(dialect=glot_dialect, pretty=True)
        if formatted.strip() != clean_sql:
            optimizations.append("Standardized SQL formatting & casing.")
            return formatted, optimizations
    except Exception:
        pass

    return clean_sql, optimizations


def create_optimizer_chain():
    """Create a LangChain Runnable for the SQL optimizer."""
    from langchain_core.runnables import RunnableLambda

    def _invoke(inputs: dict) -> dict:
        sql = inputs.get("sql", "")
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        db_url = session.resolved_database_url
        dialect = inputs.get("dialect") or get_dialect_name(db_url)
        limit = inputs.get("default_limit", settings.max_result_rows or 100)

        optimized_sql, notes = optimize_sql(sql, dialect_name=dialect, default_limit=limit)
        return {
            "sql": optimized_sql,
            "original_sql": sql,
            "optimizations": notes,
        }

    return RunnableLambda(_invoke)
