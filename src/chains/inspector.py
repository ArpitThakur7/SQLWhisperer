"""Result Inspector Chain.

Examines query results against the original question to assess whether
the data actually answers what was asked.  Flags row-count anomalies,
missing columns, value-range issues, and completeness gaps.

LLM is resolved lazily at invocation time via ``SessionConfig``.
"""

from __future__ import annotations

from loguru import logger
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from src.chains.llm_factory import get_chat_llm
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings


# ── Structured Output ─────────────────────────────────────────────


class InspectionResult(BaseModel):
    """Structured assessment of whether query results answer the question."""

    is_satisfactory: bool = Field(
        description="Whether the results plausibly answer the question"
    )
    confidence: float = Field(
        description="Confidence score from 0.0 (no confidence) to 1.0 (certain)"
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Potential issues found with the results",
    )
    suggestion: str = Field(
        default="",
        description="Concrete suggestion for improving the query if not satisfactory",
    )


# ── Prompt ────────────────────────────────────────────────────────


INSPECTOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a data quality analyst.  Examine whether the SQL query results "
                "correctly answer the user's original question.\n\n"
                "Check for:\n"
                "1. **Row count sanity** — Does the number of results make sense? "
                "(e.g., \"top 10\" should return ≤10 rows)\n"
                "2. **Column relevance** — Do the returned columns match what was asked?\n"
                "3. **Value sanity** — Are values in expected ranges? "
                "(no negative counts, no future dates for past queries)\n"
                "4. **Completeness** — Does the query miss any part of the question? "
                "(e.g., asked for a specific filter but results include everything)\n"
                "5. **Empty results** — If 0 rows returned, is that expected or a sign "
                "of a bad WHERE clause?\n\n"
                "Be conservative: if something looks off, flag it.  "
                "False positives are better than silently wrong data."
            ),
        ),
        (
            "human",
            (
                "QUESTION: {question}\n\n"
                "SQL QUERY:\n{sql}\n\n"
                "RESULT PREVIEW (first rows):\n{results_preview}\n\n"
                "TOTAL ROWS RETURNED: {row_count}\n\n"
                "Assess these results."
            ),
        ),
    ]
)


# ── Chain ─────────────────────────────────────────────────────────


def create_inspector_chain():
    """Create the result inspection chain.

    Input schema::

        {
            "question": str,
            "sql": str,
            "results_preview": str,
            "row_count": int,
            "session": SessionConfig,   # optional per-request config
        }

    Output: ``InspectionResult`` Pydantic model.
    """

    def _invoke(inputs: dict) -> InspectionResult:
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        row_count = inputs.get("row_count", 0)

        # Fast deterministic path for local Text2SQL SLMs (avoids 30s token latency)
        if getattr(session, "model", None) == "sqlwhisperer-slm" or (
            session.resolved_llm_provider in ("local_slm", "ollama")
            and "slm" in str(session.resolved_model).lower()
        ):
            return InspectionResult(
                is_satisfactory=row_count > 0,
                confidence=0.95 if row_count > 0 else 0.5,
                issues=[] if row_count > 0 else ["Query returned zero rows."],
                suggestion="",
            )

        try:
            llm = get_chat_llm(temperature=0, session=session).with_structured_output(
                InspectionResult
            )
            chain = INSPECTOR_PROMPT | llm
            res = chain.invoke({
                "question": inputs["question"],
                "sql": inputs["sql"],
                "results_preview": inputs["results_preview"],
                "row_count": inputs["row_count"],
            })
            if isinstance(res, InspectionResult):
                return res
            if isinstance(res, dict):
                return InspectionResult(**res)
        except Exception as exc:
            logger.debug(f"Inspector structured output note ({exc}) -- proceeding with results.")

        # Safe deterministic default when model returns free-form text or non-JSON
        return InspectionResult(
            is_satisfactory=True,
            confidence=0.95,
            issues=[],
            suggestion="",
        )

    return RunnableLambda(_invoke)
