"""Offensive security tests and DLP validation for SQLWhisperer."""

import pytest
from src.security.sandbox import ASTValidator, strip_sql_comments
from src.security.redactor import DataRedactor
from src.chains.executor import create_execution_chain
from src.config.session import SessionConfig


class TestASTValidator:
    def test_strip_comments(self):
        sql = "SELECT * -- this is comment\nFROM users /* multi\nline */ WHERE id = 1"
        stripped = strip_sql_comments(sql)
        assert "--" not in stripped
        assert "/*" not in stripped
        assert "SELECT * \nFROM users  WHERE id = 1" == stripped

    def test_valid_select_queries_allowed(self):
        queries = [
            "SELECT id, name FROM users WHERE active = true;",
            "SELECT count(*), department FROM employees GROUP BY department HAVING count(*) > 5;",
            "SELECT u.id, o.total FROM users u JOIN orders o ON u.id = o.user_id ORDER BY o.total DESC LIMIT 10;",
            "SELECT name FROM products WHERE id IN (SELECT product_id FROM order_items);",
            "SELECT 1 UNION ALL SELECT 2;",
        ]
        for q in queries:
            is_safe, error = ASTValidator.validate(q)
            assert is_safe is True, f"Query wrongly rejected: {q} ({error})"
            assert error is None

    def test_write_ctes_strictly_blocked(self):
        evil_queries = [
            "WITH deleted AS (DELETE FROM customers WHERE id = 1 RETURNING *) SELECT * FROM deleted;",
            "WITH inserted AS (INSERT INTO users (name) VALUES ('hack') RETURNING *) SELECT * FROM inserted;",
            "WITH updated AS (UPDATE accounts SET balance = 0 RETURNING *) SELECT * FROM updated;",
        ]
        for q in evil_queries:
            is_safe, error = ASTValidator.validate(q)
            assert is_safe is False, f"Dangerous CTE query not rejected: {q}"
            assert error is not None

    def test_multiple_statements_blocked(self):
        multi_stmt = [
            "SELECT 1; DROP TABLE orders;",
            "SELECT * FROM customers; DELETE FROM audit_log;",
            "SELECT 1; SELECT 2;",
        ]
        for q in multi_stmt:
            is_safe, error = ASTValidator.validate(q)
            assert is_safe is False, f"Multi-statement query not rejected: {q}"
            assert "multiple statements" in error.lower() or "forbidden" in error.lower()

    def test_system_catalogs_blocked(self):
        catalog_queries = [
            "SELECT * FROM pg_shadow;",
            "SELECT * FROM pg_authid;",
            "SELECT * FROM information_schema.user_mappings;",
        ]
        for q in catalog_queries:
            is_safe, error = ASTValidator.validate(q)
            assert is_safe is False, f"Catalog query not rejected: {q}"

    def test_restricted_functions_blocked(self):
        func_queries = [
            "SELECT pg_read_file('/etc/passwd');",
            "SELECT pg_sleep(10);",
            "SELECT dblink('host=evil.com', 'SELECT 1');",
        ]
        for q in func_queries:
            is_safe, error = ASTValidator.validate(q)
            assert is_safe is False, f"Restricted function query not rejected: {q}"

    def test_blocked_tables_enforced(self):
        is_safe, error = ASTValidator.validate(
            "SELECT * FROM sensitive_salaries;",
            blocked_tables=["sensitive_salaries", "admin_users"],
        )
        assert is_safe is False
        assert "restricted table 'sensitive_salaries'" in error


class TestDataRedactor:
    def test_redact_pii_values(self):
        redactor = DataRedactor(enabled=True)

        text = "Contact alice at alice@corp.com or call 555-123-4567. SSN: 123-45-6789. Card: 4111-2222-3333-4444."
        sanitized = redactor.redact_text(text)

        assert "alice@corp.com" not in sanitized
        assert "[EMAIL_REDACTED]" in sanitized

        assert "555-123-4567" not in sanitized
        assert "[PHONE_REDACTED]" in sanitized

        assert "123-45-6789" not in sanitized
        assert "[SSN_REDACTED]" in sanitized

        assert "4111-2222-3333-4444" not in sanitized
        assert "[CARD_REDACTED]" in sanitized

    def test_redact_sensitive_column_names(self):
        redactor = DataRedactor(enabled=True)
        row = {
            "id": 1,
            "username": "johndoe",
            "password": "plain_password_123",
            "api_key": "sk-123456789012345678901234",
            "email": "john@example.com",
        }
        sanitized = redactor.redact_row(row)

        assert sanitized["id"] == 1
        assert sanitized["username"] == "johndoe"
        assert sanitized["password"] == "[REDACTED_SENSITIVE_FIELD]"
        assert sanitized["api_key"] == "[REDACTED_SENSITIVE_FIELD]"
        assert sanitized["email"] == "[EMAIL_REDACTED]"


def test_executor_chain_blocks_attack(tmp_path):
    db_file = tmp_path / "test_exec.db"
    db_url = f"sqlite:///{db_file}"

    # Initialize SQLite DB
    from sqlalchemy import create_engine, text
    engine = create_engine(db_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE items (id INT, name TEXT);"))
        conn.execute(text("INSERT INTO items VALUES (1, 'Widget');"))
        conn.commit()

    chain = create_execution_chain()

    # Legitimate query executes
    res_ok = chain.invoke({"sql": "SELECT * FROM items;", "session": SessionConfig(database_url=db_url)})
    assert res_ok["success"] is True
    assert res_ok["row_count"] == 1

    # Malicious query blocked
    res_bad = chain.invoke({"sql": "DROP TABLE items;", "session": SessionConfig(database_url=db_url)})
    assert res_bad["success"] is False
    assert "forbidden" in res_bad["error"].lower()
