"""SQL Execution Chain with Zero-Trust Security Sandbox and DLP.

Runs validated SQL against the target database with multiple layers of safety:
1. Strict AST analysis via ASTValidator (sqlglot)
2. Storage engine read-only transaction mode and query statement timeouts
3. Data Loss Prevention (DLP) redaction masking sensitive customer PII and secrets
4. Query timing and bounded row caps
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from langchain_core.runnables import RunnableLambda

from src.db.connector import get_engine
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings
from src.security.sandbox import ASTValidator, enforce_read_only_session, DANGEROUS_COMMANDS_REGEX
from src.security.redactor import DataRedactor
from loguru import logger

# Aliases for backward compatibility
DANGEROUS_PATTERNS = DANGEROUS_COMMANDS_REGEX
_validate_ast_safety = ASTValidator.validate


def _execute_sql(sql: str, database_url: str | None = None) -> tuple[list[Any], list[str]]:
    """Execute a SQL query within an enforced read-only sandbox."""
    engine = get_engine(database_url)
    with engine.connect() as conn:
        # Enforce storage-level read-only session & query timeout
        enforce_read_only_session(
            conn,
            dialect_name=engine.dialect.name,
            timeout_seconds=settings.query_timeout_seconds,
        )
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = result.fetchall()
    return rows, columns


def _parse_results(rows: list[Any], columns: list[str]) -> list[dict[str, Any]]:
    """Convert SQLAlchemy result rows into a list of dicts."""
    if not rows:
        return []
    return [
        {"row": i, "data": dict(zip(columns, row))}
        for i, row in enumerate(rows)
    ]


def _format_raw_output(rows: list[Any], columns: list[str]) -> str:
    """Create a string representation of the result for display."""
    if not rows:
        return ""
    header = " | ".join(columns)
    lines = [header, "-" * len(header)]
    for row in rows[:20]:  # cap display at 20 rows
        lines.append(" | ".join(str(v) for v in row))
    if len(rows) > 20:
        lines.append(f"... ({len(rows) - 20} more rows)")
    return "\n".join(lines)


def create_execution_chain():
    """Create a safe SQL execution chain with zero-trust guardrails and DLP redaction.

    Input schema::

        {"sql": str, "session": SessionConfig}

    Output::

        {
            "results": list[dict],
            "raw_output": str,
            "row_count": int,
            "execution_time_ms": float,
            "error": str | None,
            "success": bool,
        }
    """
    redactor = DataRedactor(enabled=True)

    def _safe_execute(inputs: dict) -> dict:
        sql = inputs["sql"]
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        db_url = session.resolved_database_url

        # ── Guard 1: Strict AST analysis (single-statement, SELECT-only, no write CTEs) ──
        is_safe_ast, ast_error = ASTValidator.validate(
            sql=sql,
            blocked_tables=settings.blocked_tables,
        )
        if not is_safe_ast:
            logger.warning(f"BLOCKED query via AST Sandbox: {ast_error} | SQL: {sql[:100]}")
            return {
                "results": [],
                "raw_output": "",
                "row_count": 0,
                "execution_time_ms": 0.0,
                "error": ast_error or "Query failed security validation.",
                "success": False,
            }

        # ── Execute within Sandboxed Engine ───────────────────────
        start = time.perf_counter()
        try:
            rows, columns = _execute_sql(sql, database_url=db_url)
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            raw_results = _parse_results(rows, columns)
            capped = raw_results[: settings.max_result_rows]
            formatted_output = _format_raw_output(rows, columns)

            # ── Guard 2: Data Loss Prevention (DLP) Redaction ─────
            sanitized_results = redactor.redact_results(capped)
            sanitized_raw_output = redactor.redact_text(formatted_output)

            return {
                "results": sanitized_results,
                "raw_output": sanitized_raw_output,
                "row_count": len(raw_results),
                "execution_time_ms": round(elapsed_ms, 2),
                "error": None,
                "success": True,
            }
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.error(f"SQL execution error: {exc}")
            return {
                "results": [],
                "raw_output": "",
                "row_count": 0,
                "execution_time_ms": round(elapsed_ms, 2),
                "error": str(exc),
                "success": False,
            }

    return RunnableLambda(_safe_execute)
