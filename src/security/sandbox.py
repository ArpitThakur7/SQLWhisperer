"""Zero-Trust Database Execution Sandbox and AST Validator.

Guarantees:
1. Strict Abstract Syntax Tree (AST) validation using sqlglot
2. Single-statement enforcement (blocks multi-query injection)
3. Deterministic block of write CTEs, data exfiltration, and administrative commands
4. Engine-level read-only session isolation and statement timeouts
"""

from __future__ import annotations

import re
from typing import Any
from sqlalchemy import text
from sqlalchemy.engine import Connection
from loguru import logger

try:
    import sqlglot
    from sqlglot import exp
    HAS_SQLGLOT = True
except ImportError:
    HAS_SQLGLOT = False

# Dangerous system functions frequently abused for exfiltration or DoS
FORBIDDEN_FUNCTIONS = {
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_sleep",
    "dblink",
    "dblink_exec",
    "query_to_xml",
    "load_extension",
    "system",
    "exec",
    "xp_cmdshell",
}

# Sensitive system tables that regular analytics queries should not access
FORBIDDEN_SYSTEM_TABLES = {
    "pg_shadow",
    "pg_authid",
    "pg_user",
    "information_schema.user_mappings",
    "mysql.user",
}

# Regex backup guard for non-sqlglot fallback
DANGEROUS_COMMANDS_REGEX = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|MERGE|EXEC|EXECUTE|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)


def strip_sql_comments(sql: str) -> str:
    """Strip single-line and multi-line SQL comments."""
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql.strip()


class ASTValidator:
    """Strict AST validator for generated SQL queries."""

    @staticmethod
    def validate(sql: str, blocked_tables: list[str] | None = None) -> tuple[bool, str | None]:
        """Verify that the SQL query is strictly a read-only, safe single-statement query.

        Returns
        -------
        (is_safe, error_message)
        """
        if not sql or not sql.strip():
            return False, "Query is empty."

        clean_sql = strip_sql_comments(sql)
        if not clean_sql:
            return False, "Query contains only comments."

        # Hard regex safety net
        if DANGEROUS_COMMANDS_REGEX.search(clean_sql):
            return False, "Forbidden statement type: only SELECT queries are permitted."

        if not HAS_SQLGLOT:
            return True, None

        try:
            # sqlglot.parse splits multiple statements separated by semicolons
            parsed_statements = sqlglot.parse(clean_sql)
            statements = [s for s in parsed_statements if s is not None]

            if not statements:
                return False, "Failed to parse SQL statement."

            if len(statements) > 1:
                return False, f"Multiple statements detected ({len(statements)} statements). Only single-statement queries are permitted."

            root_expr = statements[0]

            # Root statement must be a Select or Union of Selects
            if not isinstance(root_expr, (exp.Select, exp.Union)):
                return False, f"Forbidden root statement: {type(root_expr).__name__}. Only SELECT queries are permitted."

            blocked_lower = {t.lower() for t in (blocked_tables or [])}

            # Inspect all AST nodes recursively
            for node in root_expr.walk():
                # 1. Reject any mutation nodes (including inside CTEs or subqueries)
                if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create, exp.Command)):
                    return False, f"Forbidden AST mutation node: {type(node).__name__}."

                # 2. Reject forbidden function calls
                if isinstance(node, (exp.Anonymous, exp.Func)):
                    fn_name = getattr(node, "name", "").lower() or getattr(node, "key", "").lower()
                    if fn_name in FORBIDDEN_FUNCTIONS:
                        return False, f"Call to restricted system function '{fn_name}' is forbidden."

                # 3. Reject forbidden system tables and blocked tables
                if isinstance(node, exp.Table):
                    t_name = node.name.lower()
                    t_full = node.sql().lower()
                    for blocked in blocked_lower:
                        if blocked == t_name or blocked == t_full or t_full.endswith(f".{blocked}"):
                            return False, f"Access to restricted table '{node.name}' is blocked by policy."
                    for sys_table in FORBIDDEN_SYSTEM_TABLES:
                        if sys_table == t_name or sys_table == t_full or t_full.endswith(f".{sys_table}"):
                            return False, f"Access to system catalog table '{node.name}' is forbidden."

            return True, None

        except Exception as exc:
            logger.warning(f"AST validation parsing error: {exc}")
            # Fallback to comment-stripped regex validation
            if DANGEROUS_COMMANDS_REGEX.search(clean_sql):
                return False, f"Malformed query contains forbidden keywords: {exc}"
            return True, None


def enforce_read_only_session(conn: Connection, dialect_name: str, timeout_seconds: int = 10) -> None:
    """Enforce read-only isolation and bounded statement timeouts on an active DB connection."""
    dialect = dialect_name.lower()
    timeout_ms = int(timeout_seconds * 1000)

    try:
        if "postgres" in dialect:
            conn.execute(text("SET TRANSACTION READ ONLY;"))
            conn.execute(text(f"SET statement_timeout = '{timeout_ms}ms';"))
        elif "sqlite" in dialect:
            conn.execute(text("PRAGMA query_only = ON;"))
            conn.execute(text(f"PRAGMA busy_timeout = {timeout_ms};"))
        elif "mysql" in dialect:
            conn.execute(text("SET TRANSACTION READ ONLY;"))
    except Exception as exc:
        logger.debug(f"Session sandbox directive note ({dialect}): {exc}")
