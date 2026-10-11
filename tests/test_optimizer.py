"""Tests for the SQL Query Rewriter and Optimizer."""

import pytest
from src.chains.optimizer import optimize_sql, create_optimizer_chain
from src.config.session import SessionConfig


def test_safety_limit_injection():
    sql = "SELECT id, name FROM customers WHERE country = 'USA'"
    opt_sql, notes = optimize_sql(sql, dialect_name="sqlite", default_limit=50)
    assert "LIMIT 50" in opt_sql
    assert any("LIMIT 50" in note for note in notes)


def test_scalar_aggregate_does_not_inject_redundant_limit():
    sql = "SELECT COUNT(*) FROM customers"
    opt_sql, notes = optimize_sql(sql, dialect_name="sqlite", default_limit=100)
    assert "LIMIT" not in opt_sql


def test_date_function_normalization_sqlite():
    sql = "SELECT * FROM orders WHERE created_at >= NOW()"
    opt_sql, notes = optimize_sql(sql, dialect_name="sqlite")
    assert "DATETIME('now')" in opt_sql
    assert any("NOW()" in note for note in notes)


def test_optimizer_chain_invocation():
    chain = create_optimizer_chain()
    res = chain.invoke({
        "sql": "SELECT * FROM products WHERE price > 100",
        "session": SessionConfig(database_url="sqlite:///./data/demo_ecommerce.db"),
    })
    assert "LIMIT" in res["sql"]
    assert res["original_sql"] == "SELECT * FROM products WHERE price > 100"
