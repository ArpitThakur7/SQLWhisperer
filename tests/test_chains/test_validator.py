"""Tests for the validation chain's structured output model."""

from src.chains.validator import ValidationResult


class TestValidationResult:
    """Verify the Pydantic model for validation output."""

    def test_valid_result(self):
        result = ValidationResult(
            is_valid=True,
            errors=[],
            severity="none",
            fixed_sql=None,
            reasoning="Query looks correct.",
        )
        assert result.is_valid
        assert result.severity == "none"
        assert result.fixed_sql is None

    def test_error_result(self):
        result = ValidationResult(
            is_valid=False,
            errors=["Column 'revenue' does not exist in table 'products'"],
            severity="error",
            fixed_sql="SELECT p.name, p.price FROM products p;",
            reasoning="Referenced non-existent column.",
        )
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.fixed_sql is not None

    def test_warning_result(self):
        result = ValidationResult(
            is_valid=True,
            errors=["Missing index on large table scan"],
            severity="warning",
            reasoning="Query works but may be slow.",
        )
        assert result.is_valid
        assert result.severity == "warning"
