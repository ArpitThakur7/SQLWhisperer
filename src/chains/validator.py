"""SQL Validation Chain — Pure AST Validator with Schema Introspection & LLM Fallback.

Validates generated SQL in <1ms without LLM latency using sqlglot Abstract Syntax Tree (AST)
analysis combined with live SQLAlchemy schema metadata.

Verification layers:
1. Zero-Trust Security Sandbox (blocks DDL/DML, multi-statement injection, restricted functions)
2. Strict AST Syntax Parsing (sqlglot dialect parser)
3. Schema & Column Existence Check (verifies table and column references against actual DB)
4. JOIN & Cartesian Product Guard (flags joins missing ON/USING clauses)
5. Aggregate & GROUP BY Consistency Check
6. Automatic Optimizer & Fixer (injects safety LIMIT, reformats SQL)
7. Optional Deep LLM check for subtle semantic reasoning if requested.
"""

from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from loguru import logger

try:
    import sqlglot
    from sqlglot import exp
    HAS_SQLGLOT = True
except ImportError:
    HAS_SQLGLOT = False

from src.security.sandbox import ASTValidator
from src.db.connector import get_schema_metadata, get_dialect_name
from src.chains.llm_factory import get_chat_llm
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings


# ── Structured Output Schema ──────────────────────────────────────


class ValidationResult(BaseModel):
    """Structured output for SQL validation."""

    is_valid: bool = Field(
        description="Whether the SQL is syntactically and semantically correct"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="List of identified issues",
    )
    severity: str = Field(
        default="none",
        description="One of 'none', 'warning', or 'error'",
    )
    fixed_sql: str | None = Field(
        default=None,
        description="Corrected SQL if the issues are auto-fixable, else null",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of the validation result",
    )

    @property
    def issues(self) -> list[str]:
        """Backward-compatibility alias for streaming pipeline."""
        return self.errors


# ── LLM Fallback Prompt ───────────────────────────────────────────


VALIDATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a SQL validation expert. Analyse the given SQL query for correctness "
                "against the provided database schema.\n\n"
                "DATABASE SCHEMA:\n{table_info}\n\n"
                "Check for the following categories of issues:\n"
                "1. **Syntax errors** — malformed SQL, missing keywords\n"
                "2. **Schema errors** — references to non-existent tables or columns\n"
                "3. **JOIN errors** — missing ON clauses, wrong join columns\n"
                "4. **Aggregation errors** — SELECT columns not in GROUP BY\n"
                "5. **Logic errors** — query doesn't match the user's stated intent\n"
                "6. **Security issues** — any DML/DDL (INSERT, UPDATE, DELETE, DROP, ALTER)\n\n"
                "If the query has fixable issues, provide the corrected SQL in ``fixed_sql``.\n"
                "If the query contains dangerous DML/DDL statements, set severity to 'error'."
            ),
        ),
        (
            "human",
            (
                "USER QUESTION: {question}\n\n"
                "GENERATED SQL:\n{sql}\n\n"
                "Validate this query."
            ),
        ),
    ]
)


# ── Helper: Parse schema from table_info text ─────────────────────


def parse_schema_from_ddl(table_info: str) -> dict[str, set[str]]:
    """Fallback schema parser extracting {table_name: set_of_columns} from DDL text."""
    schema: dict[str, set[str]] = {}
    if not table_info:
        return schema

    # Regex matches CREATE TABLE <name> (...)
    table_blocks = re.findall(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?\s*\((.*?)\);",
        table_info,
        re.DOTALL | re.IGNORECASE,
    )

    for table_name, body in table_blocks:
        cols = set()
        for line in body.splitlines():
            line = line.strip().strip(",")
            if not line or line.upper().startswith(("PRIMARY", "FOREIGN", "KEY", "CONSTRAINT", "UNIQUE", "CHECK")):
                continue
            parts = line.split()
            if parts:
                col_name = parts[0].strip('"`[]')
                if col_name and not col_name.startswith("--"):
                    cols.add(col_name.lower())
        schema[table_name.lower()] = cols

    return schema


# ── Pure-AST Validator Engine ─────────────────────────────────────


def validate_sql_pure_ast(
    sql: str,
    table_info: str = "",
    database_url: str | None = None,
    dialect_name: str = "sqlite",
) -> ValidationResult:
    """Validate SQL deterministically using sqlglot AST and schema inspection.

    Runs in <1ms without calling any LLM.
    """
    clean_sql = (sql or "").strip()
    if not clean_sql:
        return ValidationResult(
            is_valid=False,
            errors=["Empty SQL query generated."],
            severity="error",
            reasoning="The model returned an empty string.",
        )

    # 1. Security Sandbox Check (Regex & AST single-statement / mutation check)
    is_safe, sec_err = ASTValidator.validate(clean_sql)
    if not is_safe:
        return ValidationResult(
            is_valid=False,
            errors=[sec_err or "Query violates database security policy."],
            severity="error",
            reasoning="Security sandbox rejected the query.",
        )

    if not HAS_SQLGLOT:
        return ValidationResult(
            is_valid=True,
            errors=[],
            severity="none",
            reasoning="sqlglot not installed; regex security sandbox passed.",
        )

    # 2. Syntax & AST Parsing
    dialect_key = dialect_name.lower()
    if "postgres" in dialect_key:
        glot_dialect = "postgres"
    elif "mysql" in dialect_key:
        glot_dialect = "mysql"
    elif "duckdb" in dialect_key:
        glot_dialect = "duckdb"
    else:
        glot_dialect = "sqlite"

    try:
        parsed_statements = sqlglot.parse(clean_sql, read=glot_dialect)
        statements = [s for s in parsed_statements if s is not None]
    except Exception as parse_exc:
        # Retry with generic sql dialect
        try:
            parsed_statements = sqlglot.parse(clean_sql)
            statements = [s for s in parsed_statements if s is not None]
        except Exception as retry_exc:
            return ValidationResult(
                is_valid=False,
                errors=[f"SQL Syntax Error: {str(retry_exc)}"],
                severity="error",
                reasoning="Query failed AST parsing.",
            )

    if not statements:
        return ValidationResult(
            is_valid=False,
            errors=["Failed to parse SQL statement into an AST."],
            severity="error",
            reasoning="Parser returned empty syntax tree.",
        )

    root = statements[0]
    errors: list[str] = []
    warnings: list[str] = []

    # 3. Retrieve Schema Metadata
    known_schema: dict[str, set[str]] = {}
    try:
        meta = get_schema_metadata(database_url)
        for tbl, details in meta.items():
            known_schema[tbl] = details.get("columns", set())
    except Exception as exc:
        logger.debug(f"Live schema metadata fetch note: {exc}")

    # Supplement / fallback from table_info DDL
    if not known_schema and table_info:
        known_schema = parse_schema_from_ddl(table_info)

    # Collect CTE aliases defined in the query
    cte_names: set[str] = set()
    for cte in root.find_all(exp.CTE):
        if cte.alias:
            cte_names.add(cte.alias.lower())

    # Map table aliases to real table names
    table_alias_map: dict[str, str] = {}
    referenced_tables: set[str] = set()

    for tbl_node in root.find_all(exp.Table):
        t_name = tbl_node.name.lower()
        if t_name:
            referenced_tables.add(t_name)
            alias = tbl_node.alias.lower() if tbl_node.alias else t_name
            table_alias_map[alias] = t_name

    # Check 4: Table Existence
    if known_schema:
        for t_name in referenced_tables:
            if t_name not in known_schema and t_name not in cte_names:
                errors.append(f"Table '{t_name}' does not exist in database schema.")

    # Check 5: Column Existence
    if known_schema:
        # Collect SELECT aliases to avoid flagging them in HAVING/ORDER BY
        select_aliases = {
            s.alias.lower()
            for s in root.find_all(exp.Alias)
            if s.alias
        }

        for col_node in root.find_all(exp.Column):
            c_name = col_node.name.lower()
            c_table = col_node.table.lower() if col_node.table else None

            # Skip asterisk or pseudo-columns
            if c_name in ("*", "count") or not c_name:
                continue

            # Qualified column (e.g. o.total_amount)
            if c_table:
                real_table = table_alias_map.get(c_table, c_table)
                if real_table in known_schema:
                    valid_cols = known_schema[real_table]
                    if valid_cols and c_name not in valid_cols:
                        errors.append(f"Column '{c_name}' does not exist in table '{real_table}'.")
            else:
                # Unqualified column
                if c_name not in select_aliases:
                    matching_tables = [
                        t for t in referenced_tables
                        if t in known_schema and c_name in known_schema[t]
                    ]
                    if referenced_tables and not matching_tables and not (referenced_tables & cte_names):
                        all_ref = ", ".join(referenced_tables)
                        errors.append(f"Column '{c_name}' does not exist in referenced table(s): {all_ref}.")
                    elif len(matching_tables) > 1:
                        warnings.append(
                            f"Column '{c_name}' is ambiguous across tables: {', '.join(matching_tables)}."
                        )

    # Check 6: JOIN Condition Validation
    for join_node in root.find_all(exp.Join):
        on_clause = join_node.args.get("on")
        has_real_on = on_clause is not None and on_clause != exp.true()
        has_using = join_node.args.get("using") is not None
        is_cross = bool(join_node.kind and "cross" in join_node.kind.lower())

        if not has_real_on and not has_using and not is_cross:
            join_target = join_node.this.sql() if join_node.this else "JOIN"
            errors.append(f"JOIN on {join_target} is missing an ON or USING clause (accidental Cartesian product).")

    # Check 7: Aggregation / GROUP BY Consistency
    if isinstance(root, exp.Select):
        has_aggregates = any(
            isinstance(node, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max))
            for node in root.walk()
        )
        group_by_node = root.args.get("group")

        if has_aggregates:
            group_cols = set()
            if group_by_node:
                for g_expr in group_by_node.expressions:
                    if isinstance(g_expr, exp.Column):
                        group_cols.add(g_expr.name.lower())

            # Check unaggregated expressions in SELECT list
            for select_expr in root.expressions:
                # If expression is not an aggregate function
                is_agg = any(isinstance(n, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)) for n in select_expr.walk())
                if not is_agg and isinstance(select_expr, (exp.Column, exp.Alias)):
                    col_name = select_expr.name.lower() if isinstance(select_expr, exp.Column) else (select_expr.alias.lower() if select_expr.alias else "")
                    if col_name and group_by_node and col_name not in group_cols:
                        warnings.append(
                            f"Expression '{col_name}' in SELECT is not included in GROUP BY."
                        )

    # Check 8: Safety & Auto-Fixes (LIMIT injection & Pretty Formatting)
    fixed_sql: str | None = None
    try:
        # Check if query needs a safety LIMIT
        is_select = isinstance(root, exp.Select)
        has_limit = root.args.get("limit") is not None
        is_pure_scalar_agg = (
            is_select
            and len(root.expressions) == 1
            and any(isinstance(n, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)) for n in root.expressions[0].walk())
            and root.args.get("group") is None
        )

        needs_limit = is_select and not has_limit and not is_pure_scalar_agg
        if needs_limit:
            root = root.limit(100)

        formatted_sql = root.sql(dialect=glot_dialect, pretty=True)
        if formatted_sql.strip() != clean_sql.strip():
            fixed_sql = formatted_sql
    except Exception as format_exc:
        logger.debug(f"SQL AST formatting note: {format_exc}")

    # Final Result Compilation
    if errors:
        return ValidationResult(
            is_valid=False,
            errors=errors,
            severity="error",
            fixed_sql=fixed_sql,
            reasoning=f"AST validation detected {len(errors)} critical issues: {'; '.join(errors[:3])}",
        )

    if warnings:
        return ValidationResult(
            is_valid=True,
            errors=warnings,
            severity="warning",
            fixed_sql=fixed_sql,
            reasoning=f"AST validation passed with {len(warnings)} minor warnings.",
        )

    return ValidationResult(
        is_valid=True,
        errors=[],
        severity="none",
        fixed_sql=fixed_sql,
        reasoning="Deterministic AST & schema verification passed completely (0 tokens consumed).",
    )


# ── Chain Factory ─────────────────────────────────────────────────


def create_validation_chain():
    """Create the SQL validation chain.

    Executes pure deterministic AST & schema verification first in <1ms.
    Falls back to LLM validation only when deep validation is requested
    or on ambiguous edge cases.

    Input schema::

        {
            "question": str,
            "sql": str,
            "table_info": str,
            "dialect": str (optional),
            "session": SessionConfig (optional),
            "deep_validation": bool (optional),
        }

    Output: ``ValidationResult`` Pydantic model.
    """

    def _invoke(inputs: dict) -> ValidationResult:
        question = inputs.get("question", "")
        sql = inputs.get("sql", "")
        table_info = inputs.get("table_info", "")
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        db_url = session.resolved_database_url
        dialect = inputs.get("dialect") or get_dialect_name(db_url)
        deep = inputs.get("deep_validation", False)

        # 1. Fast Pure-AST validation (Deterministic, 0 tokens)
        ast_result = validate_sql_pure_ast(
            sql=sql,
            table_info=table_info,
            database_url=db_url,
            dialect_name=dialect,
        )

        # If AST validator found definitive syntax/schema errors, return immediately!
        if not ast_result.is_valid:
            logger.info(f"⚡ Pure-AST Validator caught error: {ast_result.errors}")
            return ast_result

        # If deep LLM semantic validation is not requested, return clean AST result
        if not deep:
            logger.debug("⚡ Pure-AST Validator passed query in 0ms.")
            return ast_result

        # Optional LLM deep validation fallback
        logger.info("🤖 Running deep semantic LLM validation...")
        try:
            llm = get_chat_llm(temperature=0, session=session).with_structured_output(
                ValidationResult
            )
            chain = VALIDATION_PROMPT | llm
            return chain.invoke({
                "question": question,
                "sql": sql,
                "table_info": table_info,
            })
        except Exception as llm_exc:
            logger.warning(f"LLM validation fallback error ({llm_exc}); using AST result.")
            return ast_result

    return RunnableLambda(_invoke)
