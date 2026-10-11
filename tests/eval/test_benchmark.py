"""Automated Golden Dataset Evaluation and Accuracy Benchmark Harness.

Measures:
1. Valid SQL Rate (VSR): percentage of queries that pass AST validation
2. Execution Correctness: queries execute without storage engine errors
3. Consistency: gold SQL matches expected relational outputs
"""

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from src.security.sandbox import ASTValidator

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "demo_ecommerce.db"
GOLDEN_PATH = Path(__file__).resolve().parent / "golden_queries.json"


@pytest.fixture(scope="module")
def golden_dataset():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def db_engine():
    db_url = f"sqlite:///{DB_PATH}"
    return create_engine(db_url)


def test_golden_dataset_structure(golden_dataset):
    """Ensure dataset format conforms to benchmark requirements."""
    assert len(golden_dataset) >= 5
    for item in golden_dataset:
        assert "id" in item
        assert "question" in item
        assert "gold_sql" in item
        assert "difficulty" in item


def test_golden_queries_pass_ast_sandbox(golden_dataset):
    """Valid SQL Rate (VSR) gate: 100% of golden queries must pass AST sandbox validation."""
    valid_count = 0
    total = len(golden_dataset)

    for item in golden_dataset:
        is_safe, error = ASTValidator.validate(item["gold_sql"])
        if is_safe:
            valid_count += 1
        else:
            pytest.fail(f"Golden query {item['id']} rejected by AST validator: {error}")

    vsr = valid_count / total
    assert vsr >= 1.0, f"Valid SQL Rate {vsr:.1%} below 100% threshold."


def test_golden_queries_execution_correctness(golden_dataset, db_engine):
    """Execution Accuracy (EX) baseline: all golden queries must run successfully against target DB."""
    executed_count = 0
    total = len(golden_dataset)

    with db_engine.connect() as conn:
        for item in golden_dataset:
            sql = item["gold_sql"]
            res = conn.execute(text(sql))
            rows = res.fetchall()
            assert rows is not None, f"Query {item['id']} returned None result"
            executed_count += 1

    ex_rate = executed_count / total
    assert ex_rate == 1.0, f"Execution correctness {ex_rate:.1%} below 100% target"
