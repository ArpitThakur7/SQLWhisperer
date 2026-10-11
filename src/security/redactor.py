"""Data Loss Prevention (DLP) & PII Redaction Engine.

Sanitizes query outputs and intermediate previews before they reach:
1. LLM Explainer and Inspector chains (preventing data leakage into context/training)
2. Vector store few-shot logs
3. Frontend UI displays
"""

from __future__ import annotations

import re
from typing import Any

# Sensitive column names that must never be shown in plaintext
SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(?i)^(password|pass_hash|secret|token|api_?key|auth_token|access_token|ssn|social_?security|credit_?card|card_number|cvv|pin)$"
)

# Value-level PII patterns
PII_RULES = [
    # US Social Security Number
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    # Credit Card Numbers (16-digit spaced/dashed or contiguous)
    (re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"), "[CARD_REDACTED]"),
    # Email Addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL_REDACTED]"),
    # Phone Numbers (US/Intl formats)
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE_REDACTED]"),
    # API Keys & Secrets
    (re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,}|gsk_[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z-_]{35})\b"), "[TOKEN_REDACTED]"),
]


class DataRedactor:
    """Enterprise Data Loss Prevention engine for masking sensitive database values."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def redact_text(self, text: str) -> str:
        """Mask all PII matches within a raw string."""
        if not self.enabled or not text:
            return text

        redacted = text
        for pattern, replacement in PII_RULES:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    def redact_value(self, column_name: str, value: Any) -> Any:
        """Redact a single cell value based on column name and content."""
        if not self.enabled:
            return value

        # 1. Column-name based hard masking
        if SENSITIVE_COLUMN_PATTERN.match(column_name.strip()):
            return "[REDACTED_SENSITIVE_FIELD]"

        # 2. String value PII inspection
        if isinstance(value, str):
            return self.redact_text(value)

        return value

    def redact_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Redact all sensitive columns and values in a row dict."""
        if not self.enabled or not isinstance(row, dict):
            return row

        return {
            col: self.redact_value(col, val)
            for col, val in row.items()
        }

    def redact_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Redact a full query result set (list of {'row': i, 'data': {...}} or flat dicts)."""
        if not self.enabled or not results:
            return results

        sanitized: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                sanitized.append(item)
                continue

            if "data" in item and isinstance(item["data"], dict):
                sanitized.append({
                    **item,
                    "data": self.redact_row(item["data"]),
                })
            else:
                sanitized.append(self.redact_row(item))

        return sanitized
