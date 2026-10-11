"""Shared test fixtures for SQLWhisperer."""

import os
import pytest
from pathlib import Path

# Ensure test env doesn't hit real services
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test.db")
os.environ.setdefault("HISTORY_DB_URL", "sqlite:///:memory:")
os.environ.setdefault("CHROMA_PERSIST_DIR", str(Path(__file__).parent / "_test_chroma"))


@pytest.fixture
def sample_question():
    """A standard test question."""
    return "Show me the top 10 products by revenue in the last 30 days"


@pytest.fixture
def sample_sql():
    """A valid SQL query matching the sample question."""
    return (
        "SELECT p.name, SUM(oi.line_total) AS revenue "
        "FROM products p "
        "JOIN order_items oi ON p.id = oi.product_id "
        "JOIN orders o ON oi.order_id = o.id "
        "WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days' "
        "GROUP BY p.id, p.name "
        "ORDER BY revenue DESC "
        "LIMIT 10;"
    )


@pytest.fixture
def sample_table_info():
    """Minimal schema info for testing."""
    return """
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    category VARCHAR(100),
    price DECIMAL(10,2)
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER,
    order_date TIMESTAMP,
    total_amount DECIMAL(10,2)
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER,
    unit_price DECIMAL(10,2),
    line_total DECIMAL(10,2)
);
"""


@pytest.fixture
def dangerous_sql_samples():
    """SQL queries that should be blocked."""
    return [
        "DELETE FROM customers WHERE id = 1;",
        "DROP TABLE orders;",
        "INSERT INTO products VALUES (1, 'hack', 'cat', 0);",
        "UPDATE customers SET tier = 'enterprise' WHERE id = 1;",
        "TRUNCATE TABLE order_items;",
        "ALTER TABLE customers ADD COLUMN hack TEXT;",
    ]
