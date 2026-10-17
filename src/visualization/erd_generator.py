"""Automatic Entity-Relationship Diagram (ERD) Generator.

Introspects target database catalog via SQLAlchemy and builds a rich, dark-mode
Graphviz DOT diagram visualizing tables, columns, data types, primary keys,
and foreign key relationship link bridges.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy import inspect
from src.db.connector import get_engine, get_schema_metadata
from loguru import logger


def generate_schema_erd(database_url: str | None = None) -> dict[str, Any]:
    """Generate a Graphviz DOT representation of the database schema ERD.

    Returns
    -------
    dict with:
      - 'dot': str (Graphviz DOT source code)
      - 'table_count': int
      - 'relationship_count': int
      - 'relationships': list of dicts describing links
    """
    engine = get_engine(database_url)
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    # Collect column details and foreign keys
    tables_data: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, str]] = []

    for table in table_names:
        try:
            columns = inspector.get_columns(table)
            pk = inspector.get_pk_constraint(table)
            pk_cols = set(pk.get("constrained_columns", [])) if pk else set()
            fks = inspector.get_foreign_keys(table)

            col_defs = []
            for col in columns:
                c_name = col["name"]
                c_type = str(col["type"])
                is_pk = c_name in pk_cols
                col_defs.append({
                    "name": c_name,
                    "type": c_type,
                    "is_pk": is_pk,
                })

            for fk in fks:
                ref_table = fk.get("referred_table")
                src_cols = fk.get("constrained_columns", [])
                ref_cols = fk.get("referred_columns", [])
                if ref_table and src_cols and ref_cols:
                    relationships.append({
                        "from_table": table,
                        "from_column": src_cols[0],
                        "to_table": ref_table,
                        "to_column": ref_cols[0],
                    })

            tables_data[table] = {
                "columns": col_defs,
                "fks": fks,
            }
        except Exception as exc:
            logger.debug(f"ERD introspection skipped table {table}: {exc}")

    # Build Graphviz DOT syntax
    dot_lines = [
        'digraph ERD {',
        '  graph [rankdir=LR, bgcolor="transparent", pad="0.4", nodesep="0.6", ranksep="1.0"];',
        '  node [shape=none, fontname="Inter, -apple-system, sans-serif", fontsize=10, fontcolor="#e2e8f0"];',
        '  edge [color="#38bdf8", arrowhead=normal, arrowsize=0.8, penwidth=1.6, fontname="Inter", fontsize=8, fontcolor="#94a3b8"];',
        '',
    ]

    # Render Table Nodes as HTML-like tables
    for table_name, data in tables_data.items():
        node_id = table_name.replace("-", "_").replace(" ", "_")
        col_rows = []
        for c in data["columns"]:
            c_name = c["name"]
            c_type = c["type"][:12]  # Truncate overly long types
            
            # Check if this column is an FK
            is_fk = any(
                fk["from_table"] == table_name and fk["from_column"] == c_name
                for fk in relationships
            )

            if c["is_pk"]:
                icon = '<font color="#fbbf24"><b>🔑</b></font> '
                style_attr = 'bgcolor="#1e293b"'
            elif is_fk:
                icon = '<font color="#a855f7"><b>🔗</b></font> '
                style_attr = ''
            else:
                icon = ''
                style_attr = ''

            col_rows.append(
                f'      <tr>'
                f'<td align="left" {style_attr} port="{c_name}">{icon}{c_name}</td>'
                f'<td align="right" {style_attr}><font color="#64748b">{c_type}</font></td>'
                f'</tr>'
            )

        col_rows_str = "\n".join(col_rows)
        dot_lines.append(
            f'  {node_id} [\n'
            f'    label=<\n'
            f'      <table border="0" cellborder="1" cellspacing="0" cellpadding="4" bgcolor="#0f172a" color="#334155" style="rounded">\n'
            f'        <tr><td bgcolor="#1e293b" colspan="2" port="header"><font color="#38bdf8" point-size="11"><b>📁 {table_name}</b></font></td></tr>\n'
            f'{col_rows_str}\n'
            f'      </table>\n'
            f'    >\n'
            f'  ];'
        )

    dot_lines.append('')

    # Render Relationship Edges
    for rel in relationships:
        src = rel["from_table"].replace("-", "_").replace(" ", "_")
        dst = rel["to_table"].replace("-", "_").replace(" ", "_")
        src_port = rel["from_column"]
        dst_port = rel["to_column"]
        dot_lines.append(
            f'  {src}:{src_port} -> {dst}:{dst_port} [label="{rel["from_column"]} ➔ {rel["to_column"]}"];'
        )

    dot_lines.append('}')
    dot_str = "\n".join(dot_lines)

    return {
        "dot": dot_str,
        "table_count": len(tables_data),
        "relationship_count": len(relationships),
        "relationships": relationships,
    }
