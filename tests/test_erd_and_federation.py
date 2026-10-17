"""Unit tests for Schema ERD Generation and Multi-DB Federation."""

import pytest
from src.visualization.erd_generator import generate_schema_erd
from src.db.federation import MultiDBFederator


def test_schema_erd_generation():
    """Verify ERD generator creates Graphviz DOT format with tables and relationships."""
    demo_url = "sqlite:///./data/demo_ecommerce.db"
    erd = generate_schema_erd(demo_url)
    assert "dot" in erd
    assert "digraph ERD" in erd["dot"]
    assert erd["table_count"] >= 3
    assert "customers" in erd["dot"]
    assert "order_items" in erd["dot"]
    assert "products" in erd["dot"]
    assert isinstance(erd["relationships"], list)


def test_federation_engine_queries():
    """Verify in-memory DuckDB can execute queries across attached SQLite tables."""
    fed = MultiDBFederator()
    catalogs = fed.list_attached()
    assert "ecommerce" in catalogs

    # Run query against attached ecommerce database
    res = fed.query("SELECT COUNT(*) AS total_customers FROM ecommerce.customers;")
    assert res["row_count"] == 1
    assert "total_customers" in res["columns"]
    assert res["results"][0]["total_customers"] > 0


def test_federation_security_blocks_unsafe_commands():
    """Verify federator blocks dangerous file export/install commands."""
    fed = MultiDBFederator()
    with pytest.raises(ValueError, match="Forbidden SQL command"):
        fed.query("COPY (SELECT * FROM ecommerce.customers) TO 'out.csv';")
