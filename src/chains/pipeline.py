"""Pipeline Orchestrator — the self-healing core of SQLWhisperer.

Wires all chains together with a refinement loop that automatically
retries on validation errors, execution failures, and suspicious
results.  Error context from previous attempts is fed back into
the Text2SQL prompt so the model doesn't repeat the same mistakes.

Now accepts a ``SessionConfig`` per request to propagate database,
LLM provider, and API key overrides without mutating global state.

Flow
----
1. Retrieve relevant schema (Schema Retriever)
2. Retrieve few-shot examples (ChromaDB)
3. Generate SQL (Text2SQL Chain)
4. Validate SQL (Validation Chain)
   └─ On error → retry with error feedback
5. Execute SQL (Execution Chain)
   └─ On error → retry with error feedback
6. Inspect results (Inspector Chain)
   └─ On suspicious → retry with suggestion
7. Explain results (Explainer Chain)
8. Save to query history (SQLite)
"""

from __future__ import annotations

from langchain_core.runnables import RunnableLambda

from src.chains.schema_retriever import create_schema_retriever
from src.chains.text2sql import create_text2sql_chain
from src.chains.optimizer import create_optimizer_chain
from src.chains.validator import create_validation_chain
from src.chains.executor import create_execution_chain
from src.chains.inspector import create_inspector_chain
from src.chains.explainer import create_explainer_chain
from src.memory.few_shot_store import FewShotStore
from src.semantic.glossary import SemanticGlossary
from src.db.history import QueryHistory
from src.db.connector import get_dialect_name
from src.config.session import SessionConfig, DEFAULT_SESSION
from src.config.settings import settings
from loguru import logger


def create_pipeline():
    """Build the full SQLWhisperer pipeline as a LangChain Runnable.

    Input schema::

        {
            "question": str,
            "session": SessionConfig | None,  # per-request overrides
        }

    Output::

        {
            "query_id": int | None,
            "question": str,
            "sql": str,
            "results": list[dict],
            "raw_output": str,
            "row_count": int,
            "execution_time_ms": float,
            "explanation": str,
            "confidence": float,
            "refinement_count": int,
            "success": bool,
            "error": str | None,
            "error_history": list[dict] | None,
        }
    """
    # ── Initialise sub-chains ─────────────────────────────────────
    # Chains now resolve LLMs lazily at invocation time, so they can
    # be shared safely across requests with different providers.
    schema_retriever = create_schema_retriever()
    text2sql = create_text2sql_chain()
    optimizer = create_optimizer_chain()
    validator = create_validation_chain()
    executor = create_execution_chain()
    inspector = create_inspector_chain()
    explainer = create_explainer_chain()
    few_shot_store = FewShotStore()
    history = QueryHistory()
    glossary = SemanticGlossary()

    def _run(inputs: dict) -> dict:
        question = inputs["question"]
        session: SessionConfig = inputs.get("session") or DEFAULT_SESSION
        db_url = session.resolved_database_url

        logger.info(f"🚀 Pipeline started | Q: {question[:100]}")

        # ── Step 1: Retrieve context (in parallel) ───────────────
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=3) as pool:
            schema_future = pool.submit(
                schema_retriever.invoke,
                {"question": question, "session": session},
            )
            few_shot_future = pool.submit(
                few_shot_store.retrieve_examples,
                question,
            )
            glossary_future = pool.submit(
                glossary.get_context,
                question,
            )

            schema_info = schema_future.result()
            few_shot_context = few_shot_future.result()
            glossary_context = glossary_future.result()

        table_context = schema_info["table_info"]
        if glossary_context:
            table_context += f"\n\n{glossary_context}"

        logger.info(
            f"📋 Context ready | tables: {schema_info['table_names']} | "
            f"few-shot chars: {len(few_shot_context)} | glossary: {bool(glossary_context)}"
        )

        # ── Refinement Loop ───────────────────────────────────────
        error_history: list[dict] = []
        final_result: dict | None = None
        sql = ""

        for attempt in range(1, settings.max_refinement_retries + 1):
            logger.info(f"🔄 Attempt {attempt}/{settings.max_refinement_retries}")

            # ── Step 2: Generate SQL ──────────────────────────────
            error_context = ""
            if error_history:
                error_context = "\n\nPREVIOUS ATTEMPTS THAT FAILED:\n"
                for err in error_history:
                    error_context += f"- SQL: {err['sql'][:200]}\n  Error: {err['error']}\n"
                error_context += "\nDo NOT repeat these mistakes. Try a different approach.\n"

            sql = text2sql.invoke(
                {
                    "question": question + error_context,
                    "table_info": table_context,
                    "few_shot_examples": few_shot_context,
                    "dialect": get_dialect_name(database_url=db_url),
                    "session": session,
                }
            )
            # Post-generation deterministic AST optimization & safety LIMIT
            opt_res = optimizer.invoke({
                "sql": sql,
                "session": session,
                "dialect": get_dialect_name(database_url=db_url),
            })
            sql = opt_res["sql"]
            if opt_res.get("optimizations"):
                logger.debug(f"⚡ Optimizer applied: {opt_res['optimizations']}")
            logger.info(f"📝 SQL ready | {sql[:150]}")

            # ── Step 3: Validate ──────────────────────────────────
            validation = validator.invoke(
                {
                    "question": question,
                    "sql": sql,
                    "table_info": table_context,
                    "session": session,
                }
            )

            if not validation.is_valid and validation.severity == "error":
                logger.warning(f"❌ Validation failed: {validation.errors}")
                if validation.fixed_sql:
                    logger.info("🔧 Using validator-suggested fix")
                    sql = validation.fixed_sql
                else:
                    error_history.append(
                        {
                            "sql": sql,
                            "error": f"Validation: {'; '.join(validation.errors)}",
                        }
                    )
                    continue  # retry from Text2SQL

            final_sql = validation.fixed_sql if validation.fixed_sql else sql

            # ── Step 4: Execute ───────────────────────────────────
            execution = executor.invoke({
                "sql": final_sql,
                "session": session,
            })

            if not execution["success"]:
                logger.warning(f"❌ Execution failed: {execution['error']}")
                error_history.append(
                    {
                        "sql": final_sql,
                        "error": f"Execution: {execution['error']}",
                    }
                )
                continue  # retry from Text2SQL

            # ── Step 5: Inspect results ───────────────────────────
            results_preview = str(execution["results"][:5])
            inspection = inspector.invoke(
                {
                    "question": question,
                    "sql": final_sql,
                    "results_preview": results_preview,
                    "row_count": execution["row_count"],
                    "session": session,
                }
            )

            if (
                not inspection.is_satisfactory
                and attempt < settings.max_refinement_retries
            ):
                logger.warning(f"⚠️ Inspection issues: {inspection.issues}")
                error_history.append(
                    {
                        "sql": final_sql,
                        "error": (
                            f"Inspection: {'; '.join(inspection.issues)}. "
                            f"Suggestion: {inspection.suggestion}"
                        ),
                    }
                )
                continue  # retry from Text2SQL

            # ── Step 6: Explain ───────────────────────────────────
            explanation = explainer.invoke(
                {
                    "question": question,
                    "sql": final_sql,
                    "results_preview": results_preview,
                    "row_count": execution["row_count"],
                    "execution_time_ms": execution["execution_time_ms"],
                    "session": session,
                }
            )

            final_result = {
                "question": question,
                "sql": final_sql,
                "results": execution["results"],
                "raw_output": execution.get("raw_output", ""),
                "row_count": execution["row_count"],
                "execution_time_ms": execution["execution_time_ms"],
                "explanation": explanation,
                "confidence": inspection.confidence,
                "refinement_count": attempt - 1,
                "success": True,
                "error": None,
            }
            break  # ✅ success — exit refinement loop

        # ── Fallback: all retries exhausted ───────────────────────
        if final_result is None:
            logger.error(
                f"💀 All {settings.max_refinement_retries} attempts exhausted"
            )
            final_result = {
                "question": question,
                "sql": error_history[-1]["sql"] if error_history else sql,
                "results": [],
                "raw_output": "",
                "row_count": 0,
                "execution_time_ms": 0.0,
                "explanation": (
                    "I was unable to generate a correct query after "
                    f"{settings.max_refinement_retries} attempts. "
                    "Please try rephrasing your question or providing more detail."
                ),
                "error_history": error_history,
                "confidence": 0.0,
                "refinement_count": settings.max_refinement_retries,
                "success": False,
                "error": "Max retries exhausted",
            }

        # ── Step 7: Save to history ───────────────────────────────
        try:
            query_id = history.save_query(
                {
                    "question": question,
                    "generated_sql": sql,
                    "final_sql": final_result.get("sql", ""),
                    "results_preview": str(
                        final_result.get("results", [])[:5]
                    ),
                    "row_count": final_result.get("row_count", 0),
                    "execution_time_ms": final_result.get(
                        "execution_time_ms", 0.0
                    ),
                    "was_successful": final_result["success"],
                    "confidence": final_result.get("confidence", 0.0),
                    "refinement_count": final_result.get(
                        "refinement_count", 0
                    ),
                    "explanation": final_result.get("explanation", ""),
                }
            )
            final_result["query_id"] = query_id
        except Exception as exc:
            logger.error(f"Failed to save history: {exc}")
            final_result["query_id"] = None

        logger.info(
            f"✅ Pipeline complete | success={final_result['success']} | "
            f"confidence={final_result.get('confidence', 0):.2f} | "
            f"retries={final_result.get('refinement_count', 0)}"
        )
        return final_result

    return RunnableLambda(_run)


async def stream_pipeline(question: str, session: SessionConfig | None = None):
    """Async generator yielding real-time pipeline lifecycle events for SSE streaming."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    session_cfg = session or DEFAULT_SESSION
    db_url = session_cfg.resolved_database_url

    yield {
        "stage": "started",
        "status": "running",
        "message": f"Query processing started for: {question[:80]}",
    }

    # Reusable sub-chains
    schema_retriever = create_schema_retriever()
    text2sql = create_text2sql_chain()
    optimizer = create_optimizer_chain()
    validator = create_validation_chain()
    executor = create_execution_chain()
    inspector = create_inspector_chain()
    explainer = create_explainer_chain()
    few_shot_store = FewShotStore()
    history = QueryHistory()
    glossary = SemanticGlossary()

    # Step 1: Parallel Context Retrieval
    yield {
        "stage": "context_retrieval",
        "status": "running",
        "message": "Introspecting database schema and matching few-shot examples...",
    }

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=3) as pool:
        schema_fut = loop.run_in_executor(
            pool, schema_retriever.invoke, {"question": question, "session": session_cfg}
        )
        few_shot_fut = loop.run_in_executor(
            pool, few_shot_store.retrieve_examples, question
        )
        glossary_fut = loop.run_in_executor(
            pool, glossary.get_context, question
        )

        schema_info, few_shot_context, glossary_context = await asyncio.gather(
            schema_fut, few_shot_fut, glossary_fut
        )

    table_context = schema_info["table_info"]
    if glossary_context:
        table_context += f"\n\n{glossary_context}"

    yield {
        "stage": "context_retrieval",
        "status": "done",
        "tables": schema_info["table_names"],
        "message": f"Identified relevant tables: {', '.join(schema_info['table_names'])}",
    }

    error_history: list[dict] = []
    final_result: dict | None = None
    sql = ""

    for attempt in range(1, settings.max_refinement_retries + 1):
        yield {
            "stage": "sql_generation",
            "status": "running",
            "attempt": attempt,
            "message": f"Drafting SQL query (attempt {attempt}/{settings.max_refinement_retries})...",
        }

        error_context = ""
        if error_history:
            error_context = "\n\nPREVIOUS ATTEMPTS THAT FAILED:\n"
            for err in error_history:
                error_context += f"- SQL: {err['sql'][:200]}\n  Error: {err['error']}\n"
            error_context += "\nDo NOT repeat these mistakes. Try a different approach.\n"

        sql = await asyncio.to_thread(
            text2sql.invoke,
            {
                "question": question + error_context,
                "table_info": table_context,
                "few_shot_examples": few_shot_context,
                "dialect": get_dialect_name(database_url=db_url),
                "session": session_cfg,
            },
        )

        # Post-generation deterministic AST optimization & safety LIMIT
        opt_res = await asyncio.to_thread(
            optimizer.invoke,
            {
                "sql": sql,
                "session": session_cfg,
                "dialect": get_dialect_name(database_url=db_url),
            },
        )
        sql = opt_res["sql"]

        yield {
            "stage": "sql_generation",
            "status": "done",
            "attempt": attempt,
            "sql": sql,
            "message": "SQL query draft completed & optimized.",
        }

        # Step 3: Validate
        yield {
            "stage": "validation",
            "status": "running",
            "message": "Validating SQL syntax and security constraints...",
        }

        validation = await asyncio.to_thread(
            validator.invoke,
            {
                "question": question,
                "sql": sql,
                "table_info": table_context,
                "dialect": get_dialect_name(database_url=db_url),
                "session": session_cfg,
            },
        )

        if not validation.is_valid:
            if validation.fixed_sql:
                sql = validation.fixed_sql
                yield {
                    "stage": "validation",
                    "status": "passed",
                    "message": "SQL auto-corrected by AST self-healing engine.",
                }
            else:
                yield {
                    "stage": "validation",
                    "status": "warning",
                    "issues": validation.issues,
                    "severity": validation.severity,
                    "message": f"Validation issues detected: {'; '.join(validation.issues)}",
                }
                error_history.append({
                    "sql": sql,
                    "error": f"Validation ({validation.severity}): {'; '.join(validation.issues)}",
                })
                continue

        yield {
            "stage": "validation",
            "status": "passed",
            "message": "SQL syntax and security validation passed.",
        }

        final_sql = validation.fixed_sql if validation.fixed_sql else sql

        # Step 4: Execute
        yield {
            "stage": "execution",
            "status": "running",
            "message": "Executing query in sandboxed database engine...",
        }

        execution = await asyncio.to_thread(
            executor.invoke,
            {"sql": final_sql, "session": session_cfg},
        )

        if not execution["success"]:
            yield {
                "stage": "execution",
                "status": "failed",
                "error": execution["error"],
                "message": f"Execution error: {execution['error']}",
            }
            error_history.append({"sql": final_sql, "error": f"Execution: {execution['error']}"})
            continue

        yield {
            "stage": "execution",
            "status": "done",
            "row_count": execution["row_count"],
            "execution_time_ms": execution["execution_time_ms"],
            "message": f"Executed in {execution['execution_time_ms']:.1f}ms returning {execution['row_count']} rows.",
        }

        # Step 5: Inspect
        results_preview = str(execution["results"][:5])
        inspection = await asyncio.to_thread(
            inspector.invoke,
            {
                "question": question,
                "sql": final_sql,
                "results_preview": results_preview,
                "row_count": execution["row_count"],
                "session": session_cfg,
            },
        )

        if not inspection.is_satisfactory and attempt < settings.max_refinement_retries:
            yield {
                "stage": "inspection",
                "status": "warning",
                "issues": inspection.issues,
                "message": f"Anomalies detected: {'; '.join(inspection.issues)}",
            }
            error_history.append({
                "sql": final_sql,
                "error": f"Inspection: {'; '.join(inspection.issues)}. Suggestion: {inspection.suggestion}",
            })
            continue

        # Step 6: Explain
        yield {
            "stage": "explanation",
            "status": "running",
            "message": "Synthesizing plain-English explanation...",
        }

        explanation = await asyncio.to_thread(
            explainer.invoke,
            {
                "question": question,
                "sql": final_sql,
                "results_preview": results_preview,
                "row_count": execution["row_count"],
                "execution_time_ms": execution["execution_time_ms"],
                "session": session_cfg,
            },
        )

        final_result = {
            "question": question,
            "sql": final_sql,
            "results": execution["results"],
            "raw_output": execution.get("raw_output", ""),
            "row_count": execution["row_count"],
            "execution_time_ms": execution["execution_time_ms"],
            "explanation": explanation,
            "confidence": inspection.confidence,
            "refinement_count": attempt - 1,
            "success": True,
            "error": None,
        }
        break

    if final_result is None:
        final_result = {
            "question": question,
            "sql": error_history[-1]["sql"] if error_history else sql,
            "results": [],
            "raw_output": "",
            "row_count": 0,
            "execution_time_ms": 0.0,
            "explanation": "Unable to generate a satisfactory query within retry budget.",
            "error_history": error_history,
            "confidence": 0.0,
            "refinement_count": settings.max_refinement_retries,
            "success": False,
            "error": "Max retries exhausted",
        }

    # Save to history
    try:
        query_id = history.save_query({
            "question": question,
            "generated_sql": sql,
            "final_sql": final_result.get("sql", ""),
            "results_preview": str(final_result.get("results", [])[:5]),
            "row_count": final_result.get("row_count", 0),
            "execution_time_ms": final_result.get("execution_time_ms", 0.0),
            "was_successful": final_result["success"],
            "confidence": final_result.get("confidence", 0.0),
            "refinement_count": final_result.get("refinement_count", 0),
            "explanation": final_result.get("explanation", ""),
        })
        final_result["query_id"] = query_id
    except Exception:
        final_result["query_id"] = None

    yield {
        "stage": "complete",
        "status": "success" if final_result["success"] else "failed",
        "result": final_result,
        "message": "Query pipeline execution finished.",
    }
