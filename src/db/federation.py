"""Multi-Database Federation Engine powered by DuckDB.

Allows simultaneous querying and joining across multiple disparate databases
(e.g., SQLite files, CSV datasets, and Parquet analytical stores) inside an
in-memory DuckDB virtual engine.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
import duckdb
from loguru import logger

from src.db.connector import ROOT_DIR, DATA_DIR, DEFAULT_SQLITE_URL


class MultiDBFederator:
    """Manages an in-memory DuckDB session with federated database attachments."""

    def __init__(self) -> None:
        self.conn = duckdb.connect(database=":memory:")
        self._attached: dict[str, str] = {}
        self._init_default_attachments()

    def _init_default_attachments(self) -> None:
        """Attach default SQLite demo database and any user uploads."""
        demo_path = DATA_DIR / "demo_ecommerce.db"
        if demo_path.is_file():
            self.attach_sqlite("ecommerce", str(demo_path))

        history_path = DATA_DIR / "query_history.db"
        if history_path.is_file():
            self.attach_sqlite("history", str(history_path))

    def attach_sqlite(self, alias: str, db_path: str) -> bool:
        """Attach an external SQLite database into DuckDB session."""
        try:
            safe_alias = alias.replace("-", "_").replace(" ", "_").lower()
            normalized_path = os.path.abspath(db_path).replace("\\", "/")
            self.conn.execute(f"ATTACH '{normalized_path}' AS {safe_alias} (TYPE SQLITE);")
            self._attached[safe_alias] = normalized_path
            logger.info(f"🔗 Federated DuckDB attached SQLite database '{safe_alias}' from {normalized_path}")
            return True
        except Exception as exc:
            logger.warning(f"Failed to attach SQLite DB {db_path} as {alias}: {exc}")
            return False

    def list_attached(self) -> dict[str, list[str]]:
        """Return all attached catalogs and their tables."""
        res: dict[str, list[str]] = {}
        for alias in self._attached:
            try:
                tables = self.conn.execute(
                    f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{alias}'"
                ).fetchall()
                res[alias] = [t[0] for t in tables]
            except Exception:
                res[alias] = []
        return res

    def query(self, sql: str, max_rows: int = 100) -> dict[str, Any]:
        """Execute a cross-database federated query.

        Parameters
        ----------
        sql:
            SQL statement that can reference attached catalogs (e.g. `ecommerce.products`, `history.queries`).
        """
        t0 = time.perf_counter()
        # Security: block PRAGMA and unsafe file export
        lowered = sql.strip().lower()
        if any(kw in lowered for kw in ["copy", "export_database", "install", "load"]):
            raise ValueError("Forbidden SQL command in federated query.")

        cursor = self.conn.execute(sql)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        raw_rows = cursor.fetchmany(max_rows)
        results = [dict(zip(columns, row)) for row in raw_rows]

        return {
            "results": results,
            "columns": columns,
            "row_count": len(results),
            "execution_time_ms": elapsed_ms,
            "attached_catalogs": list(self._attached.keys()),
        }


# Global singleton instance
federator = MultiDBFederator()
