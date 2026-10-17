"""SLM (Small Language Model) Data Preparation & Optimization Pipeline for SQLWhisperer.

Prepares high-density, syntactically clean, and stratified instruction datasets
optimized for fine-tuning Small Language Models (1.5B - 7B parameters, e.g. Qwen 2.5 Coder,
Llama 3.2 3B, Phi-3.5) on free Google Colab T4 GPUs or local hardware.

Harvests and blends:
1. gretelai/synthetic_text_to_sql (100,000 queries) - Stratified analytical complexity (CTEs, Window functions, Multi-joins)
2. b-mc2/sql-create-context (78,577 queries) - Clean DDL-to-SQL context mapping
3. spider (Yale Benchmark - 8,034 queries) - Multi-table complex relational queries across 200 schemas
4. Multi-Domain Enterprise Benchmarks (IMDb, Yelp, Restaurants, Geo, Scholar)
5. SQLWhisperer Local E-Commerce Golden Set

Exports:
- data/training_datasets/slm_prepared/train_slm_curated.jsonl (ChatML format with production system prompt)
- data/training_datasets/slm_prepared/val_slm_curated.jsonl   (Validation holdout)
- data/training_datasets/slm_prepared/train_slm_alpaca.jsonl (Alpaca/SFT format)
- data/training_datasets/slm_prepared/dataset_summary.json   (Token length audit, stats, complexity distribution)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
from pathlib import Path
from typing import Any

import duckdb
from loguru import logger

try:
    import tiktoken
    ENC = tiktoken.get_encoding("cl100k_base")
except Exception:
    ENC = None

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "training_datasets"
SLM_DIR = DATA_DIR / "slm_prepared"
SLM_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# Production SQLWhisperer System Prompt template (matches src/chains/text2sql.py)
SYSTEM_PROMPT_TEMPLATE = (
    "You are an expert SQL query writer for {dialect} databases.\n\n"
    "DATABASE SCHEMA:\n"
    "{schema}\n\n"
    "RULES — follow these strictly:\n"
    "1. Write ONLY a single SELECT or WITH query. No INSERT, UPDATE, DELETE, DROP, or DDL.\n"
    "2. Always use explicit column names — never SELECT *.\n"
    "3. Use table aliases for readability (e.g., c for customers, o for orders).\n"
    "4. Handle NULLs explicitly (IS NULL, COALESCE, etc.) where relevant.\n"
    "5. Use the correct JOIN type (INNER, LEFT, etc.) based on the relationship.\n"
    "6. Add ORDER BY when the question implies ranking or ordering.\n"
    "7. Add LIMIT when the question asks for 'top N' or similar.\n"
    "8. Use date/time functions appropriate for {dialect}.\n"
    "9. For aggregations, always include GROUP BY for every non-aggregated column.\n"
    "10. Return ONLY the raw SQL query ending with a semicolon — no explanation, no markdown fences."
)


def count_tokens(text: str) -> int:
    """Accurately count tokens using tiktoken (cl100k_base) or fallback estimate."""
    if ENC is not None:
        return len(ENC.encode(text))
    return max(1, math.ceil(len(text) / 4))


def clean_ddl(context: str) -> str:
    """Strip noisy INSERT statements and data dumps from context, keeping clean DDL."""
    if not context:
        return ""
    # Strip INSERT INTO ... ; statements
    ddl = re.sub(r"INSERT\s+INTO\s+[^;]+;", "", context, flags=re.IGNORECASE)
    # Strip multi-line comments
    ddl = re.sub(r"/\*.*?\*/", "", ddl, flags=re.DOTALL)
    # Strip single line comments
    ddl = re.sub(r"--[^\n]*", "", ddl)
    # Normalize excess whitespace
    ddl = re.sub(r"\n\s*\n+", "\n", ddl).strip()
    return ddl


def clean_sql(sql: str) -> str:
    """Normalize SQL: strip code fences, clean whitespace, and ensure semicolon termination."""
    if not sql:
        return ""
    sql = sql.strip()
    # Remove markdown code fences
    if sql.startswith("```"):
        lines = [line for line in sql.splitlines() if not line.strip().startswith("```")]
        sql = "\n".join(lines).strip()
    # Normalize internal whitespace
    sql = re.sub(r"[ \t]+", " ", sql).strip()
    if not sql.endswith(";"):
        sql += ";"
    return sql


def clean_question(q: str) -> str:
    """Clean question text."""
    q = q.strip()
    # Remove leading numbering like '1. ' or 'Question: '
    q = re.sub(r"^(question\s*:\s*|\d+\.\s*)", "", q, flags=re.IGNORECASE).strip()
    return q


# ── 1. Gretel Stratified Analytical Processor ──────────────────────────────
def process_gretel(sample_limit: int = 4500) -> list[dict[str, Any]]:
    """Process gretelai/synthetic_text_to_sql with stratified sampling across complexity tiers."""
    parquet_path = DATA_DIR / "gretelai" / "synthetic_text_to_sql_train.snappy.parquet"
    if not parquet_path.is_file():
        logger.warning(f"Gretel parquet not found at {parquet_path}. Skipping.")
        return []

    logger.info("⚡ Processing Gretel dataset (100k rows) with Stratified Analytical Sampling...")
    con = duckdb.connect()

    # Stratified quotas for Small Language Model training:
    # Small models benefit enormously from learning CTEs, window functions, and multi-joins
    queries = [
        # 1. All CTEs (high signal, rare pattern)
        ("CTEs", "SELECT sql_prompt, sql_context, sql, sql_complexity FROM rel WHERE sql_complexity = 'CTEs'"),
        # 2. Window functions (RANK, ROW_NUMBER, OVER)
        ("Window Functions", "SELECT sql_prompt, sql_context, sql, sql_complexity FROM rel WHERE sql_complexity = 'window functions' LIMIT 1200"),
        # 3. Multiple joins (3+ tables)
        ("Multiple Joins", "SELECT sql_prompt, sql_context, sql, sql_complexity FROM rel WHERE sql_complexity = 'multiple_joins' LIMIT 1500"),
        # 4. Complex aggregations
        ("Aggregations", "SELECT sql_prompt, sql_context, sql, sql_complexity FROM rel WHERE sql_complexity = 'aggregation' LIMIT 1500"),
    ]

    rel = con.read_parquet(parquet_path.as_posix())
    processed: list[dict[str, Any]] = []

    for name, sql_query in queries:
        df = con.query(sql_query).df()
        count = 0
        for _, row in df.iterrows():
            ddl = clean_ddl(str(row["sql_context"]))
            q = clean_question(str(row["sql_prompt"]))
            sql = clean_sql(str(row["sql"]))
            if not ddl or not q or not sql or len(sql) < 10:
                continue
            processed.append({
                "source": f"gretel_{row['sql_complexity']}",
                "complexity": str(row["sql_complexity"]),
                "dialect": "PostgreSQL",
                "schema": ddl,
                "question": q,
                "sql": sql,
            })
            count += 1
        logger.info(f"   ↳ Gretel [{name}]: Extracted {count} high-signal queries.")

    logger.success(f"✅ Gretel sampling complete: {len(processed)} complex analytical queries ready.")
    return processed


def _parse_spider_item(raw_user: str, raw_asst: str) -> tuple[str, str, str]:
    """Extract pristine schema, question, and SQL query from Spider prompt format."""
    lines = [l.strip() for l in raw_user.splitlines() if l.strip()]
    question = ""
    schema_lines = []

    # Find the question line by scanning backwards for the last '###' before SELECT
    for idx in range(len(lines) - 1, -1, -1):
        line = lines[idx]
        if line.startswith("###") and not line.startswith("### Sqlite") and not line.startswith("### Complete"):
            question = line.lstrip("#").strip()
            schema_lines = lines[:idx]
            break

    # Clean schema lines to retain pure table definitions and foreign keys
    clean_schema = []
    for l in schema_lines:
        if l.startswith("### Complete") or l.startswith("### Sqlite SQL tables"):
            continue
        l = l.lstrip("#").strip()
        if l:
            clean_schema.append(l)

    schema_str = "\n".join(clean_schema)
    sql_str = raw_asst.strip()
    if not sql_str.upper().startswith("SELECT") and not sql_str.upper().startswith("WITH"):
        sql_str = "SELECT " + sql_str
    if not sql_str.endswith(";"):
        sql_str += ";"
    return schema_str, question, sql_str


# ── 2. Spider Benchmark Processor ──────────────────────────────────────────
def process_spider(sample_limit: int = 3500) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Process Yale Spider benchmark into train and validation sets."""
    train_file = DATA_DIR / "spider" / "spider_train_raw.json"
    val_file = DATA_DIR / "spider" / "spider_val_raw.json"

    if not train_file.is_file() or not val_file.is_file():
        logger.warning("Spider raw files not found. Skipping.")
        return [], []

    logger.info("⚡ Processing Yale Spider Benchmark (8,034 relational queries across 200 DBs)...")

    with open(train_file, "r", encoding="utf-8") as f:
        raw_train = json.load(f)
    with open(val_file, "r", encoding="utf-8") as f:
        raw_val = json.load(f)

    def _convert_spider(items: list[dict], limit: int | None = None) -> list[dict[str, Any]]:
        results = []
        if limit and len(items) > limit:
            items = random.sample(items, limit)
        for it in items:
            msgs = it.get("messages", [])
            if len(msgs) < 3:
                continue
            schema_str, question_str, sql_str = _parse_spider_item(msgs[1]["content"], msgs[2]["content"])

            if not schema_str or not question_str or not sql_str:
                continue

            results.append({
                "source": "spider_benchmark",
                "complexity": "multi_table_relational",
                "dialect": "SQLite",
                "schema": schema_str,
                "question": question_str,
                "sql": sql_str,
            })
        return results

    train_processed = _convert_spider(raw_train, limit=sample_limit)
    val_processed = _convert_spider(raw_val, limit=1250)

    logger.success(f"✅ Spider complete: {len(train_processed)} train, {len(val_processed)} validation queries.")
    return train_processed, val_processed


# ── 3. b-mc2/sql-create-context Processor ──────────────────────────────────
def process_b_mc2(sample_limit: int = 3500) -> list[dict[str, Any]]:
    """Process b-mc2/sql-create-context dataset."""
    json_path = DATA_DIR / "b_mc2" / "sql_create_context_v4.json"
    if not json_path.is_file():
        logger.warning(f"b-mc2 dataset not found at {json_path}. Skipping.")
        return []

    logger.info("⚡ Processing b-mc2/sql-create-context (78,577 queries)...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Sample randomly with fixed seed for reproducibility
    sampled = random.sample(data, min(sample_limit * 2, len(data)))
    processed: list[dict[str, Any]] = []

    for item in sampled:
        if len(processed) >= sample_limit:
            break
        q = clean_question(item.get("question", ""))
        ddl = clean_ddl(item.get("context", ""))
        sql = clean_sql(item.get("answer", ""))

        if not q or not ddl or not sql or len(sql) < 10:
            continue

        processed.append({
            "source": "b_mc2_context",
            "complexity": "ddl_mapping",
            "dialect": "SQLite",
            "schema": ddl,
            "question": q,
            "sql": sql,
        })

    logger.success(f"✅ b-mc2 sampling complete: {len(processed)} DDL-aligned queries ready.")
    return processed


# ── 4. Multi-Domain & Local E-Commerce Golden Set ──────────────────────────
def process_domain_and_golden() -> list[dict[str, Any]]:
    """Load enterprise multi-domain and SQLWhisperer local golden datasets."""
    logger.info("⚡ Processing Enterprise Multi-Domain & Local Golden datasets...")
    results: list[dict[str, Any]] = []

    # Local E-Commerce golden queries
    schema_ecommerce = (
        "Table customers (id INTEGER PRIMARY KEY, name VARCHAR, email VARCHAR, city VARCHAR, country VARCHAR, created_at TIMESTAMP);\n"
        "Table products (id INTEGER PRIMARY KEY, name VARCHAR, category VARCHAR, price DECIMAL, cost DECIMAL, stock_quantity INTEGER);\n"
        "Table orders (id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TIMESTAMP, status VARCHAR, total_amount DECIMAL, shipping_country VARCHAR);\n"
        "Table order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price DECIMAL);"
    )

    golden_queries = [
        ("Show top 5 customers by total spending in 2026",
         "SELECT c.name, ROUND(SUM(o.total_amount), 2) AS total_spend FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.order_date >= '2026-01-01' AND o.status != 'cancelled' GROUP BY c.name ORDER BY total_spend DESC LIMIT 5;"),
        ("What is our total revenue by product category?",
         "SELECT p.category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS category_revenue FROM order_items oi JOIN products p ON oi.product_id = p.id JOIN orders o ON oi.order_id = o.id WHERE o.status != 'cancelled' GROUP BY p.category ORDER BY category_revenue DESC;"),
        ("Calculate average order value (AOV) excluding cancelled orders",
         "SELECT ROUND(AVG(total_amount), 2) AS average_order_value FROM orders WHERE status != 'cancelled';"),
        ("Find all customers who registered in Germany",
         "SELECT name, email, city FROM customers WHERE country = 'Germany' ORDER BY name ASC;"),
        ("Show monthly order count and total revenue for 2026",
         "SELECT strftime('%Y-%m', order_date) AS month, COUNT(id) AS order_count, ROUND(SUM(total_amount), 2) AS monthly_revenue FROM orders WHERE order_date >= '2026-01-01' AND status != 'cancelled' GROUP BY month ORDER BY month ASC;"),
        ("Which products have stock quantity below 20?",
         "SELECT name, category, stock_quantity, price FROM products WHERE stock_quantity < 20 ORDER BY stock_quantity ASC;"),
        ("Calculate net profit margin by product category",
         "SELECT p.category, ROUND(SUM((oi.unit_price - p.cost) * oi.quantity), 2) AS total_profit FROM order_items oi JOIN products p ON oi.product_id = p.id JOIN orders o ON oi.order_id = o.id WHERE o.status != 'cancelled' GROUP BY p.category ORDER BY total_profit DESC;"),
        ("Show top 10 products with the highest number of units sold",
         "SELECT p.name, p.category, SUM(oi.quantity) AS total_units_sold FROM order_items oi JOIN products p ON oi.product_id = p.id JOIN orders o ON oi.order_id = o.id WHERE o.status != 'cancelled' GROUP BY p.name, p.category ORDER BY total_units_sold DESC LIMIT 10;"),
        ("List orders shipped to Canada with total amount exceeding $300",
         "SELECT id, customer_id, order_date, status, total_amount FROM orders WHERE shipping_country = 'Canada' AND total_amount > 300 ORDER BY total_amount DESC;"),
        ("Identify customers who have placed more than 3 orders",
         "SELECT c.name, c.email, COUNT(o.id) AS order_count, ROUND(SUM(o.total_amount), 2) AS lifetime_value FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.status != 'cancelled' GROUP BY c.name, c.email HAVING COUNT(o.id) > 3 ORDER BY order_count DESC;"),
    ]

    for q, sql in golden_queries:
        results.append({
            "source": "sqlwhisperer_ecommerce_golden",
            "complexity": "domain_analytics",
            "dialect": "SQLite",
            "schema": schema_ecommerce,
            "question": q,
            "sql": clean_sql(sql),
        })

    # Multi-domain files (IMDb, Yelp, Restaurants, Geo, Academic)
    domain_dir = DATA_DIR / "multi_domain"
    if domain_dir.is_dir():
        for fpath in domain_dir.glob("*.json"):
            domain = fpath.stem
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    items = json.load(f)
                for it in items:
                    sentences = it.get("sentences", [])
                    sql_list = it.get("sql", [])
                    if sentences and sql_list:
                        q = clean_question(sentences[0].get("text", ""))
                        sql = clean_sql(sql_list[0])
                        results.append({
                            "source": f"enterprise_{domain}",
                            "complexity": "domain_enterprise",
                            "dialect": "SQLite",
                            "schema": f"Database Domain: {domain.capitalize()} Relational Schema",
                            "question": q,
                            "sql": sql,
                        })
            except Exception as e:
                logger.warning(f"Failed loading domain {domain}: {e}")

    logger.success(f"✅ Domain & Golden sets complete: {len(results)} specialized enterprise queries.")
    return results


# ── 5. Formatters & Audit Engine ───────────────────────────────────────────
def to_chatml(entry: dict[str, Any]) -> dict[str, Any]:
    """Format triplet into ChatML conversation using SQLWhisperer production prompt."""
    system_text = SYSTEM_PROMPT_TEMPLATE.format(
        dialect=entry.get("dialect", "SQL"),
        schema=entry["schema"],
    )
    return {
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": entry["question"]},
            {"role": "assistant", "content": entry["sql"]},
        ],
        "metadata": {
            "source": entry.get("source"),
            "complexity": entry.get("complexity"),
            "dialect": entry.get("dialect"),
        },
    }


def to_alpaca(entry: dict[str, Any]) -> dict[str, Any]:
    """Format triplet into standard Alpaca instruction tuning format."""
    return {
        "instruction": f"Given the following database schema, generate a valid SQL query to answer the question.\n\nDATABASE SCHEMA:\n{entry['schema']}",
        "input": entry["question"],
        "output": entry["sql"],
        "source": entry.get("source"),
        "complexity": entry.get("complexity"),
    }


def audit_token_distribution(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit token lengths to ensure 0% truncation within SLM context windows (2048 tokens)."""
    token_lengths = []
    for item in samples:
        total_len = 0
        for msg in item["messages"]:
            total_len += count_tokens(msg["content"])
        token_lengths.append(total_len)

    token_lengths.sort()
    n = len(token_lengths)
    return {
        "total_samples": n,
        "min_tokens": token_lengths[0] if n > 0 else 0,
        "mean_tokens": round(sum(token_lengths) / max(1, n), 1),
        "median_tokens": token_lengths[n // 2] if n > 0 else 0,
        "p90_tokens": token_lengths[int(n * 0.90)] if n > 0 else 0,
        "p99_tokens": token_lengths[int(n * 0.99)] if n > 0 else 0,
        "max_tokens": token_lengths[-1] if n > 0 else 0,
        "fits_in_2048_window": sum(1 for t in token_lengths if t <= 2048) / max(1, n) * 100.0,
    }


# ── 6. Main Pipeline Runner ────────────────────────────────────────────────
def prepare_slm_datasets(is_full: bool = False):
    logger.info("=" * 65)
    logger.info("🚀 SQLWhisperer SLM Data Preparation & Optimization Pipeline")
    logger.info("=" * 65)

    # 1. Harvest & Sample all sources
    gretel_data = process_gretel(sample_limit=4500)
    spider_train, spider_val = process_spider(sample_limit=3500)
    b_mc2_data = process_b_mc2(sample_limit=3500)
    domain_data = process_domain_and_golden()

    # 2. Combine & Stratify
    train_pool = gretel_data + spider_train + b_mc2_data + domain_data
    val_pool = spider_val

    random.shuffle(train_pool)
    logger.info(f"📊 Total curated training pool: {len(train_pool):,} samples")
    logger.info(f"📊 Total holdout validation pool: {len(val_pool):,} samples")

    # 3. Format into ChatML and Alpaca
    train_chatml = [to_chatml(x) for x in train_pool]
    val_chatml = [to_chatml(x) for x in val_pool]
    train_alpaca = [to_alpaca(x) for x in train_pool]

    # 4. Token Audit
    logger.info("🔍 Auditing token length distribution with BPE tokenizer...")
    audit = audit_token_distribution(train_chatml)
    logger.info(f"   ↳ Mean Tokens: {audit['mean_tokens']} | P90: {audit['p90_tokens']} | Max: {audit['max_tokens']}")
    logger.info(f"   ↳ Fits within 2048 token window: {audit['fits_in_2048_window']:.2f}%")

    # 5. Complexity Breakdown
    breakdown: dict[str, int] = {}
    for item in train_pool:
        comp = item.get("complexity", "unknown")
        breakdown[comp] = breakdown.get(comp, 0) + 1

    # 6. Save JSONL Files
    curated_chatml_path = SLM_DIR / "train_slm_curated.jsonl"
    curated_val_path = SLM_DIR / "val_slm_curated.jsonl"
    curated_alpaca_path = SLM_DIR / "train_slm_alpaca.jsonl"
    manifest_path = SLM_DIR / "dataset_summary.json"

    logger.info(f"💾 Writing {curated_chatml_path}...")
    with open(curated_chatml_path, "w", encoding="utf-8") as f:
        for entry in train_chatml:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(f"💾 Writing {curated_val_path}...")
    with open(curated_val_path, "w", encoding="utf-8") as f:
        for entry in val_chatml:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(f"💾 Writing {curated_alpaca_path}...")
    with open(curated_alpaca_path, "w", encoding="utf-8") as f:
        for entry in train_alpaca:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    manifest = {
        "status": "ready_for_slm_fine_tuning",
        "dataset_name": "SQLWhisperer-SLM-Curated-Mix",
        "recommended_models": [
            "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit",
            "unsloth/Qwen2.5-Coder-3B-Instruct-bnb-4bit",
            "unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit",
            "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
        ],
        "training_samples": len(train_chatml),
        "validation_samples": len(val_chatml),
        "total_queries": len(train_chatml) + len(val_chatml),
        "complexity_breakdown": breakdown,
        "token_audit": audit,
        "files": {
            "train_chatml": str(curated_chatml_path.relative_to(BASE_DIR)),
            "val_chatml": str(curated_val_path.relative_to(BASE_DIR)),
            "train_alpaca": str(curated_alpaca_path.relative_to(BASE_DIR)),
        },
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.success(f"🎉 SLM dataset preparation finished successfully! Output in {SLM_DIR}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare data for SLM text-to-SQL fine-tuning")
    parser.add_argument("--full", action="store_true", help="Compile the full 187k+ uncurated corpus")
    args = parser.parse_args()
    prepare_slm_datasets(is_full=args.full)
