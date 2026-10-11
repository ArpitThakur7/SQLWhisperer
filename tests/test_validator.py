"""Tests for the Pure-AST SQL Validator."""

import pytest
from src.chains.validator import validate_sql_pure_ast, create_validation_chain
from src.config.session import SessionConfig

DB_URL = "sqlite:///./data/demo_ecommerce.db"


def test_valid_select_query():
    sql = "SELECT id, name, email FROM customers WHERE country = 'Germany' LIMIT 10"
    res = validate_sql_pure_ast(sql, database_url=DB_URL, dialect_name="sqlite")
    assert res.is_valid is True
    assert res.severity == "none"
    assert len(res.errors) == 0


def test_missing_table_detected():
    sql = "SELECT * FROM non_existent_table LIMIT 10"
    res = validate_sql_pure_ast(sql, database_url=DB_URL, dialect_name="sqlite")
    assert res.is_valid is False
    assert any("non_existent_table" in err for err in res.errors)


def test_missing_column_detected():
    sql = "SELECT c.fake_column_name FROM customers c LIMIT 10"
    res = validate_sql_pure_ast(sql, database_url=DB_URL, dialect_name="sqlite")
    assert res.is_valid is False
    assert any("fake_column_name" in err for err in res.errors)


def test_cartesian_join_blocked():
    sql = "SELECT * FROM customers c JOIN orders o"
    res = validate_sql_pure_ast(sql, database_url=DB_URL, dialect_name="sqlite")
    assert res.is_valid is False
    assert any("missing an ON" in err for err in res.errors)


def test_security_sandbox_blocks_mutations():
    for dangerous_sql in [
        "DROP TABLE customers;",
        "INSERT INTO customers (name) VALUES ('Hacker');",
        "DELETE FROM orders;",
        "UPDATE products SET price = 0;",
    ]:
        res = validate_sql_pure_ast(dangerous_sql, database_url=DB_URL, dialect_name="sqlite")
        assert res.is_valid is False


def test_validator_issues_property_compatibility():
    sql = "DROP TABLE orders;"
    res = validate_sql_pure_ast(sql, database_url=DB_URL, dialect_name="sqlite")
    assert res.issues == res.errors
