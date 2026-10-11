"""Tests for the SQL execution chain's safety guardrails.

These tests verify the regex blocklist and table blocklist
without requiring a real database connection.
"""

from src.chains.executor import DANGEROUS_PATTERNS, _parse_results, _format_raw_output


class TestDangerousPatternDetection:
    """Verify that the regex blocklist catches all dangerous SQL."""

    def test_blocks_delete(self):
        assert DANGEROUS_PATTERNS.search("DELETE FROM customers WHERE id = 1")

    def test_blocks_drop(self):
        assert DANGEROUS_PATTERNS.search("DROP TABLE orders")

    def test_blocks_insert(self):
        assert DANGEROUS_PATTERNS.search("INSERT INTO products VALUES (1, 'a', 'b', 0)")

    def test_blocks_update(self):
        assert DANGEROUS_PATTERNS.search("UPDATE customers SET tier = 'pro'")

    def test_blocks_truncate(self):
        assert DANGEROUS_PATTERNS.search("TRUNCATE TABLE order_items")

    def test_blocks_alter(self):
        assert DANGEROUS_PATTERNS.search("ALTER TABLE customers ADD COLUMN hack TEXT")

    def test_blocks_grant(self):
        assert DANGEROUS_PATTERNS.search("GRANT ALL ON customers TO hacker")

    def test_blocks_execute(self):
        assert DANGEROUS_PATTERNS.search("EXECUTE sp_dangerous_proc")

    def test_allows_select(self):
        safe_sql = "SELECT c.full_name, COUNT(*) FROM customers c GROUP BY c.full_name"
        assert DANGEROUS_PATTERNS.search(safe_sql) is None

    def test_allows_select_with_subquery(self):
        safe_sql = (
            "SELECT * FROM (SELECT id, name FROM products) sub "
            "WHERE sub.id > 10"
        )
        assert DANGEROUS_PATTERNS.search(safe_sql) is None

    def test_allows_select_with_case(self):
        safe_sql = (
            "SELECT CASE WHEN status = 'active' THEN 1 ELSE 0 END "
            "FROM customers"
        )
        assert DANGEROUS_PATTERNS.search(safe_sql) is None

    def test_blocks_case_insensitive(self):
        assert DANGEROUS_PATTERNS.search("delete from customers")
        assert DANGEROUS_PATTERNS.search("Drop Table orders")
        assert DANGEROUS_PATTERNS.search("INSERT into products values (1)")

    def test_all_dangerous_samples(self, dangerous_sql_samples):
        """Parametrised test using the fixture."""
        for sql in dangerous_sql_samples:
            assert DANGEROUS_PATTERNS.search(sql), f"Should block: {sql}"


class TestResultParsing:
    """Test the result parser without a database."""

    def test_parse_empty_rows(self):
        assert _parse_results([], ["id", "name"]) == []

    def test_parse_rows_with_columns(self):
        rows = [(1, "Widget"), (2, "Gadget")]
        columns = ["id", "name"]
        results = _parse_results(rows, columns)
        assert len(results) == 2
        assert results[0]["row"] == 0
        assert results[0]["data"] == {"id": 1, "name": "Widget"}
        assert results[1]["row"] == 1
        assert results[1]["data"] == {"id": 2, "name": "Gadget"}

    def test_parse_single_row(self):
        rows = [(42,)]
        columns = ["count"]
        results = _parse_results(rows, columns)
        assert len(results) == 1
        assert results[0]["data"] == {"count": 42}


class TestFormatRawOutput:
    """Test the raw output formatting."""

    def test_empty_rows(self):
        assert _format_raw_output([], ["id"]) == ""

    def test_with_data(self):
        rows = [(1, "Widget", 19.99), (2, "Gadget", 29.99)]
        columns = ["id", "name", "price"]
        output = _format_raw_output(rows, columns)
        assert "id | name | price" in output
        assert "Widget" in output
        assert "Gadget" in output

    def test_truncates_at_20_rows(self):
        rows = [(i, f"item_{i}") for i in range(30)]
        columns = ["id", "name"]
        output = _format_raw_output(rows, columns)
        assert "10 more rows" in output


class TestASTValidation:
    """Test AST-level SQL validation using sqlglot."""

    def test_allows_valid_select(self):
        from src.chains.executor import _validate_ast_safety
        is_safe, error = _validate_ast_safety("SELECT id, name FROM customers WHERE tier = 'pro'")
        assert is_safe is True
        assert error is None

    def test_blocks_dml_in_ast(self):
        from src.chains.executor import _validate_ast_safety
        is_safe, error = _validate_ast_safety("UPDATE customers SET tier = 'pro'")
        assert is_safe is False
        assert "Forbidden statement type" in error or "Only SELECT" in error

    def test_blocks_subquery_mutation(self):
        from src.chains.executor import _validate_ast_safety
        is_safe, error = _validate_ast_safety("SELECT * FROM (DELETE FROM orders RETURNING *)")
        assert is_safe is False

