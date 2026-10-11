"""User feedback handler.

Bridges the feedback API endpoint to the few-shot store and
query history, closing the learning loop.
"""

from src.memory.few_shot_store import FewShotStore
from src.db.history import QueryHistory
from loguru import logger


class FeedbackHandler:
    """Processes user feedback to improve future SQL generation."""

    def __init__(
        self,
        few_shot_store: FewShotStore | None = None,
        history: QueryHistory | None = None,
    ) -> None:
        self._few_shot_store = few_shot_store or FewShotStore()
        self._history = history or QueryHistory()

    def handle_feedback(
        self,
        query_id: int,
        feedback: str,
        corrected_sql: str | None = None,
    ) -> dict:
        """Process feedback and update stores.

        Parameters
        ----------
        query_id:
            ID of the query record to update.
        feedback:
            One of ``'positive'``, ``'negative'``, ``'corrected'``.
        corrected_sql:
            User-provided corrected SQL (required when feedback is ``'corrected'``).

        Returns
        -------
        dict with ``status`` and ``message`` keys.
        """
        # 1. Update history record
        self._history.update_feedback(query_id, feedback, corrected_sql)

        # 2. Retrieve the original record for context
        record = self._history.get_by_id(query_id)
        if record is None:
            return {"status": "error", "message": f"Query #{query_id} not found"}

        # 3. Learn from positive feedback
        if feedback == "positive":
            self._few_shot_store.add_example(
                question=record.question,
                sql=record.final_sql,
                explanation=record.explanation or "",
                source="positive_feedback",
            )
            logger.info(f"Learned from positive feedback on query #{query_id}")
            return {"status": "ok", "message": "Thanks! This will improve future queries."}

        # 4. Learn from corrections
        if feedback == "corrected" and corrected_sql:
            self._few_shot_store.add_example(
                question=record.question,
                sql=corrected_sql,
                explanation="User-corrected query",
                source="correction",
            )
            logger.info(f"Learned from correction on query #{query_id}")
            return {"status": "ok", "message": "Correction saved. Future queries will benefit."}

        # 5. Negative feedback — just logged, no learning yet
        if feedback == "negative":
            logger.info(f"Negative feedback on query #{query_id} — logged for analysis")
            return {"status": "ok", "message": "Noted. Try rephrasing your question."}

        return {"status": "ok", "message": f"Feedback '{feedback}' recorded"}
