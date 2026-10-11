"""Explanation Chain.

Generates a plain-English summary of the SQL query and its results,
aimed at non-technical readers.  Includes key findings, performance
notes, and caveats.

LLM is resolved lazily at invocation time via ``SessionConfig``.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

from src.chains.llm_factory import get_chat_llm
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings


EXPLAINER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a data analyst writing for a non-technical audience.\n"
                "Given a SQL query and its results, provide a clear summary with:\n\n"
                "1. **What this query does** (2–3 sentences, plain English, no SQL jargon)\n"
                "2. **Key findings** (bullet points of notable insights from the results)\n"
                "3. **Performance notes** (execution time context, potential optimisation tips)\n"
                "4. **Caveats** (any assumptions, NULL handling, date boundaries to be aware of)\n\n"
                "Keep it concise and actionable.  The reader should understand the data "
                "without ever looking at the SQL."
            ),
        ),
        (
            "human",
            (
                "ORIGINAL QUESTION: {question}\n\n"
                "SQL:\n{sql}\n\n"
                "RESULTS ({row_count} rows, executed in {execution_time_ms}ms):\n"
                "{results_preview}\n\n"
                "Explain these results."
            ),
        ),
    ]
)


def create_explainer_chain():
    """Create the explanation chain.

    Input schema::

        {
            "question": str,
            "sql": str,
            "results_preview": str,
            "row_count": int,
            "execution_time_ms": float,
            "session": SessionConfig,   # optional per-request config
        }

    Output: ``str`` — plain-English explanation.
    """

    def _invoke(inputs: dict) -> str:
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        llm = get_chat_llm(temperature=0.3, session=session)
        chain = EXPLAINER_PROMPT | llm | StrOutputParser()
        return chain.invoke({
            "question": inputs["question"],
            "sql": inputs["sql"],
            "results_preview": inputs["results_preview"],
            "row_count": inputs["row_count"],
            "execution_time_ms": inputs["execution_time_ms"],
        })

    return RunnableLambda(_invoke)
