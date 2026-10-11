"""Text-to-SQL Generation Chain.

Converts a natural language question into a syntactically correct SQL query
using schema context and (optionally) few-shot examples retrieved from
ChromaDB.

LLM is resolved lazily at invocation time via ``SessionConfig`` to support
per-request model switching.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

from src.chains.llm_factory import get_chat_llm
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings


TEXT2SQL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are an expert SQL query writer for {dialect} databases.\n\n"
                "DATABASE SCHEMA:\n{table_info}\n\n"
                "{few_shot_examples}\n\n"
                "RULES — follow these strictly:\n"
                "1. Write ONLY a single SELECT query. No INSERT, UPDATE, DELETE, DROP, or DDL.\n"
                "2. Always use explicit column names — never SELECT *.\n"
                "3. Use table aliases for readability (e.g., c for customers, o for orders).\n"
                "4. Handle NULLs explicitly (IS NULL, COALESCE, etc.) where relevant.\n"
                "5. Use the correct JOIN type (INNER, LEFT, etc.) based on the relationship.\n"
                "6. Add ORDER BY when the question implies ranking or ordering.\n"
                "7. Add LIMIT when the question asks for \"top N\" or similar.\n"
                "8. Use date/time functions appropriate for {dialect}.\n"
                "9. For aggregations, always include GROUP BY for every non-aggregated column.\n"
                "10. Return ONLY the raw SQL query — no explanation, no markdown fences, no comments."
            ),
        ),
        ("human", "{question}"),
    ]
)


def _normalise_sql(sql: str) -> str:
    """Strip whitespace/fences and ensure the query ends with a semicolon."""
    sql = sql.strip()
    # Remove markdown code fences if the model slipped them in
    if sql.startswith("```"):
        lines = sql.split("\n")
        sql = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )
    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    return sql


def create_text2sql_chain():
    """Create the Text-to-SQL generation chain.

    Input schema::

        {
            "question": str,
            "table_info": str,
            "few_shot_examples": str,   # may be empty
            "dialect": str,             # e.g. "PostgreSQL"
            "session": SessionConfig,   # optional per-request config
        }

    Output: ``str`` — a raw SQL SELECT query.
    """

    def _invoke(inputs: dict) -> str:
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        llm = get_chat_llm(session=session)
        chain = TEXT2SQL_PROMPT | llm | StrOutputParser()
        raw_sql = chain.invoke({
            "question": inputs["question"],
            "table_info": inputs["table_info"],
            "few_shot_examples": inputs["few_shot_examples"],
            "dialect": inputs["dialect"],
        })
        return _normalise_sql(raw_sql)

    return RunnableLambda(_invoke)
