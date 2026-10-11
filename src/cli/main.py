"""SQLWhisperer Command-Line Interface (CLI).

Allows data engineers and analysts to execute natural-language queries directly
from the terminal, export results, or generate SQL queries for automation workflows.

Usage:
    sqlwhisperer query "Show top 5 customers by spend"
    sqlwhisperer query "Products with stock < 20" --sql-only
    sqlwhisperer query "Total revenue this month" --explain
    sqlwhisperer health
"""

import argparse
import json
import sys
from pathlib import Path


def cmd_query(args):
    """Execute a natural-language query through the SQLWhisperer pipeline."""
    from src.config.settings import settings

    if args.db:
        settings.database_url = args.db

    from src.chains.pipeline import create_pipeline

    if not args.json and not args.sql_only:
        print(f"\n[*] Processing query: \"{args.question}\"...")

    pipeline = create_pipeline()
    result = pipeline.invoke({"question": args.question})

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    if args.sql_only:
        if result.get("sql"):
            print(result["sql"])
        else:
            print(f"-- Error: {result.get('error')}", file=sys.stderr)
            sys.exit(1)
        return

    print("\n" + "=" * 65)
    print(" [*] SQLWhisperer Query Results")
    print("=" * 65)

    if not result.get("success"):
        print(f"\n[!] Query Failed: {result.get('error')}")
        if result.get("sql"):
            print(f"    Attempted SQL: {result['sql']}")
        sys.exit(1)

    print(f"\n[SQL Query]:\n{result.get('sql')}\n")
    print(f"[Results ({result.get('row_count', 0)} rows, {result.get('execution_time_ms', 0)}ms)]:")
    print(result.get("raw_output", "(no rows returned)"))

    if args.explain and result.get("explanation"):
        print("\n" + "-" * 65)
        print("[Plain-English Summary]:")
        print(result["explanation"])

    print("=" * 65)


def cmd_health(args):
    """Check connectivity to LLM, Database, and Memory stores."""
    print("=" * 65)
    print(" [*] SQLWhisperer System Diagnostics")
    print("=" * 65)

    from src.config.settings import settings
    from src.db.connector import get_dialect_name, get_table_names

    print(f" LLM Provider:       {settings.llm_provider.upper()} ({settings.openai_model if settings.llm_provider == 'openai' else settings.ollama_model})")
    print(f" Target Database:    {settings.database_url}")
    print(f" Detected Dialect:   {get_dialect_name()}")

    # Test Database
    try:
        tables = get_table_names()
        print(f" Database Status:    ONLINE ({len(tables)} tables: {', '.join(tables[:5])})")
    except Exception as exc:
        print(f" Database Status:    OFFLINE ({exc})")

    # Test History Store
    history_file = Path("./data/query_history.db")
    print(f" History Store:      {'INITIALIZED' if history_file.exists() else 'PENDING LAUNCH'}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        prog="sqlwhisperer",
        description="SQLWhisperer: Natural Language to Production SQL + Self-Healing",
    )
    parser.add_argument("--version", action="version", version="sqlwhisperer 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # query command
    query_parser = subparsers.add_parser("query", help="Convert natural language to SQL and execute")
    query_parser.add_argument("question", type=str, help="Natural language question to ask")
    query_parser.add_argument("--db", type=str, help="Override target database connection URL")
    query_parser.add_argument("--explain", action="store_true", help="Print plain-English summary")
    query_parser.add_argument("--sql-only", action="store_true", help="Output only raw SQL query")
    query_parser.add_argument("--json", action="store_true", help="Output result as JSON")
    query_parser.set_defaults(func=cmd_query)

    # health command
    health_parser = subparsers.add_parser("health", help="Run system and connectivity checks")
    health_parser.set_defaults(func=cmd_health)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
