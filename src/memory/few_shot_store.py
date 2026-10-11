"""ChromaDB-backed few-shot example store.

Stores successful question→SQL pairs as embeddings and retrieves
the most semantically similar examples at query time to improve
SQL generation accuracy.
"""

from langchain_core.documents import Document
from src.config.settings import settings
from loguru import logger


class LocalChromaEmbeddings:
    """Zero-setup local embeddings using ChromaDB's ONNX all-MiniLM-L6-v2."""

    def __init__(self) -> None:
        from chromadb.utils import embedding_functions
        self._ef = embedding_functions.DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vec)) for vec in self._ef(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [float(x) for x in self._ef([text])[0]]


class FewShotStore:
    """Manages few-shot SQL examples in ChromaDB for retrieval-augmented generation."""

    def __init__(self) -> None:
        self._vectorstore = None
        self._retriever = None
        try:
            from langchain_chroma import Chroma

            # Prefer OpenAI if a real key is present; otherwise use 100% free local embeddings
            has_real_openai = bool(
                settings.openai_api_key
                and settings.openai_api_key.startswith("sk-")
                and len(settings.openai_api_key) > 25
            )

            if has_real_openai:
                try:
                    from langchain_openai import OpenAIEmbeddings
                    self._embeddings = OpenAIEmbeddings(
                        model="text-embedding-3-small",
                        api_key=settings.openai_api_key,
                    )
                    logger.debug("Using OpenAI text-embedding-3-small for few-shot store.")
                except Exception:
                    self._embeddings = LocalChromaEmbeddings()
                    logger.info("Using local all-MiniLM-L6-v2 embeddings for few-shot store.")
            else:
                self._embeddings = LocalChromaEmbeddings()
                logger.info("Using local all-MiniLM-L6-v2 embeddings for few-shot store.")

            self._vectorstore = Chroma(
                collection_name=settings.chroma_collection_name,
                embedding_function=self._embeddings,
                persist_directory=settings.chroma_persist_dir,
            )
            self._retriever = self._vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 3},
            )
        except Exception as exc:
            logger.warning(f"ChromaDB few-shot store initialized in offline/fallback mode: {exc}")

    # ── Write ─────────────────────────────────────────────────────

    def add_example(
        self,
        question: str,
        sql: str,
        explanation: str = "",
        source: str = "user_feedback",
    ) -> None:
        """Store a successful query as a few-shot example."""
        if not self._vectorstore:
            logger.warning("Vector store unavailable, skipping example addition.")
            return

        doc = Document(
            page_content=question,
            metadata={
                "sql": sql,
                "explanation": explanation,
                "source": source,
            },
        )
        try:
            self._vectorstore.add_documents([doc])
            logger.info(f"Added few-shot example: {question[:80]}...")
        except Exception as e:
            logger.warning(f"Failed to add few-shot example to ChromaDB: {e}")

    def seed_examples(self, examples: list[dict]) -> None:
        """Bulk-load initial few-shot examples."""
        if not self._vectorstore:
            logger.warning("Vector store unavailable, skipping example seeding.")
            return

        docs = [
            Document(
                page_content=ex["question"],
                metadata={
                    "sql": ex["sql"],
                    "explanation": ex.get("explanation", ""),
                    "source": "seed",
                },
            )
            for ex in examples
        ]
        try:
            self._vectorstore.add_documents(docs)
            logger.info(f"Seeded {len(docs)} few-shot examples")
        except Exception as e:
            logger.warning(f"Failed to seed examples into ChromaDB: {e}")

    def _switch_to_local(self) -> None:
        """Switch embedding function and vector store to local embeddings."""
        try:
            from langchain_chroma import Chroma
            self._embeddings = LocalChromaEmbeddings()
            self._vectorstore = Chroma(
                collection_name=f"{settings.chroma_collection_name}_local",
                embedding_function=self._embeddings,
                persist_directory=f"{settings.chroma_persist_dir}_local",
            )
            self._retriever = self._vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 3},
            )
            logger.info("Successfully switched few-shot store to local embeddings.")
        except Exception as exc:
            logger.warning(f"Could not switch to local embeddings: {exc}")

    # ── Read ──────────────────────────────────────────────────────

    def retrieve_examples(self, question: str, k: int = 3) -> str:
        """Retrieve the most relevant few-shot examples formatted for the prompt."""
        if not self._retriever:
            return ""

        try:
            docs = self._retriever.invoke(question)
        except Exception as e:
            err_str = str(e)
            if "Incorrect API key" in err_str or "401" in err_str or "AuthenticationError" in type(e).__name__:
                logger.info("OpenAI API key invalid; auto-switching few-shot store to local embeddings.")
                self._switch_to_local()
                try:
                    docs = self._retriever.invoke(question)
                except Exception:
                    return ""
            else:
                logger.warning(f"Few-shot retrieval failed: {e}")
                return ""

        if not docs:
            return ""

        lines = ["SIMILAR QUERIES FOR REFERENCE:"]
        for i, doc in enumerate(docs[:k], 1):
            lines.append(f"\nExample {i}:")
            lines.append(f"  Question: {doc.page_content}")
            lines.append(f"  SQL: {doc.metadata.get('sql', 'N/A')}")

        return "\n".join(lines)

    @property
    def count(self) -> int:
        """Return the number of examples currently stored."""
        if not self._vectorstore:
            return 0
        try:
            return self._vectorstore._collection.count()
        except Exception:
            return 0
