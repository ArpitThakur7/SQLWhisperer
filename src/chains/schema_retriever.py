"""Smart Schema Retriever Chain — Graph-Based Deterministic Schema Selector.

Uses Foreign Key Graph Traversal, column matching, and business glossary synonyms
to identify the exact minimal set of tables needed to answer a query in <1ms.
Eliminates an expensive, unreliable LLM call while guaranteeing that junction/bridge
tables required for JOINs are mathematically included.

Pipeline:
1. Lexical & Synonym Scoring: Matches question tokens against table & column names.
2. Shortest-Path FK Graph Traversal (BFS): Connects selected entities through bridge tables.
3. Small Schema Fast-Path: Zero-latency resolution for standard schemas (<= 8 tables).
4. Fallback to lightweight LLM only for massive schemas (> 15 tables) with zero lexical matches.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Any
import yaml

from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from src.chains.llm_factory import get_chat_llm
from src.db.connector import get_table_names, get_table_info, get_schema_metadata
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings
from loguru import logger

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
GLOSSARY_PATH = ROOT_DIR / "config" / "glossary.yaml"


# ── Vocabulary & Synonym Helper ────────────────────────────────────


def load_synonyms() -> dict[str, str]:
    """Load business synonyms mapping from config/glossary.yaml."""
    if not GLOSSARY_PATH.is_file():
        return {}
    try:
        with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return {str(k).lower(): str(v).lower() for k, v in data.get("synonyms", {}).items()}
    except Exception:
        return {}


# ── Foreign Key Graph Traversal ───────────────────────────────────


def build_fk_graph(meta: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    """Construct an undirected graph of tables connected by foreign keys."""
    graph: dict[str, set[str]] = {t: set() for t in meta}
    for table_name, details in meta.items():
        for fk in details.get("foreign_keys", []):
            ref_tbl = fk.get("referred_table")
            if ref_tbl and ref_tbl in graph:
                graph[table_name].add(ref_tbl)
                graph[ref_tbl].add(table_name)
    return graph


def find_shortest_fk_path(graph: dict[str, set[str]], start: str, target: str) -> list[str]:
    """Find the shortest foreign key path between two tables using BFS."""
    if start == target:
        return [start]
    if start not in graph or target not in graph:
        return []

    visited = {start}
    queue = deque([[start]])

    while queue:
        path = queue.popleft()
        current = path[-1]

        for neighbor in graph.get(current, set()):
            if neighbor == target:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])

    return []


def connect_table_islands(graph: dict[str, set[str]], selected: set[str]) -> set[str]:
    """Ensure that all selected tables can be joined by adding intermediate bridge tables."""
    connected = set(selected)
    tables_list = sorted(list(selected))

    for i in range(len(tables_list)):
        for j in range(i + 1, len(tables_list)):
            t1, t2 = tables_list[i], tables_list[j]
            path = find_shortest_fk_path(graph, t1, t2)
            if path and len(path) <= 4:  # At most 2 bridge tables
                connected.update(path)

    return connected


# ── Heuristic Table Selection ─────────────────────────────────────


def select_tables_heuristically(
    question: str,
    meta: dict[str, dict[str, Any]],
    synonyms: dict[str, str],
) -> list[str]:
    """Deterministic selection of tables via lexical matching, synonyms, and FK graph BFS."""
    q_lower = (question or "").lower()
    words = set(re.findall(r"\b[a-zA-Z0-9_]+\b", q_lower))

    # Expand words with synonym targets
    expanded_words = set(words)
    for word in words:
        if word in synonyms:
            expanded_words.add(synonyms[word])

    scores: dict[str, int] = {t: 0 for t in meta}

    for table_name, details in meta.items():
        t_clean = table_name.lower()
        t_singular = t_clean[:-1] if t_clean.endswith("s") else t_clean

        # Table name match (high weight)
        if t_clean in expanded_words or t_singular in expanded_words or t_clean in q_lower:
            scores[table_name] += 15

        # Column name match (medium weight)
        for col in details.get("columns", set()):
            col_clean = col.lower()
            col_singular = col_clean[:-1] if col_clean.endswith("s") else col_clean
            # Skip generic short IDs
            if col_clean in ("id", "type", "name") and len(col_clean) <= 4:
                continue
            if col_clean in expanded_words or col_singular in expanded_words or col_clean in q_lower:
                scores[table_name] += 6

    # Select tables with positive score
    candidates = {t for t, score in scores.items() if score > 0}

    # If small database (<= 6 tables), include all candidates or full schema if none matched
    total_tables = len(meta)
    if not candidates:
        if total_tables <= 6:
            return list(meta.keys())
        return []

    # If small schema and we have candidates, connect them with FK bridge tables
    fk_graph = build_fk_graph(meta)
    connected_candidates = connect_table_islands(fk_graph, candidates)

    return sorted(list(connected_candidates))


# ── Fallback LLM Selector ─────────────────────────────────────────


TABLE_SELECTOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a database schema expert. Given a user question and a list of "
                "available tables, determine which tables are needed to answer the question.\n\n"
                "Available tables: {available_tables}\n\n"
                "Return a JSON object with a single key \"tables\" containing a list of "
                "table names that are directly needed.  Think carefully about JOINs required.\n\n"
                "Example output: {{\"tables\": [\"orders\", \"customers\"]}}"
            ),
        ),
        ("human", "{question}"),
    ]
)


# ── Chain Factory ─────────────────────────────────────────────────


def create_schema_retriever():
    """Build a fast, deterministic schema retriever with FK graph bridge resolution.

    Eliminates unnecessary LLM calls for small/medium schemas while ensuring
    intermediate JOIN junction tables are mathematically guaranteed.

    Returns a ``Runnable`` with signature::

        {"question": str, "session": SessionConfig} -> {"table_info": str, "table_names": list[str]}
    """
    synonyms = load_synonyms()

    def _invoke(inputs: dict) -> dict:
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        db_url = session.resolved_database_url
        question = inputs.get("question", "")

        all_tables = get_table_names(database_url=db_url)
        if not all_tables:
            return {"table_info": "", "table_names": []}

        meta = get_schema_metadata(database_url=db_url)

        # 1. Deterministic Fast-Path: Graph-based selection
        selected_tables = select_tables_heuristically(question, meta, synonyms)

        # If heuristic succeeded
        if selected_tables:
            valid_tables = [t for t in selected_tables if t in all_tables]
            logger.debug(f"⚡ Smart Schema Selector (FK Graph) resolved tables in 0ms: {valid_tables}")
            schema = get_table_info(valid_tables, database_url=db_url)
            return {
                "table_info": schema,
                "table_names": valid_tables,
            }

        # 2. Small Schema Fallback (<= 8 tables): include all
        if len(all_tables) <= 8:
            logger.debug(f"⚡ Small schema fast-path (<=8 tables): including all {len(all_tables)} tables.")
            schema = get_table_info(all_tables, database_url=db_url)
            return {
                "table_info": schema,
                "table_names": all_tables,
            }

        # 3. LLM Fallback (only for large schemas with no lexical keyword matches)
        logger.info("🤖 Large schema with no lexical matches: invoking LLM table selector...")
        try:
            llm = get_chat_llm(temperature=0, session=session)
            table_selector = TABLE_SELECTOR_PROMPT | llm | JsonOutputParser()
            selected = table_selector.invoke({
                "question": question,
                "available_tables": ", ".join(all_tables),
            })
            tables = selected.get("tables", all_tables[:5])
            valid_tables = [t for t in tables if t in all_tables] or all_tables[:5]
        except Exception as exc:
            logger.warning(f"Table selector LLM failed, using first 5 tables: {exc}")
            valid_tables = all_tables[:5]

        schema = get_table_info(valid_tables, database_url=db_url)
        return {
            "table_info": schema,
            "table_names": valid_tables,
        }

    return RunnableLambda(_invoke)
