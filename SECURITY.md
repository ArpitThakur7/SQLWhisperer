# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

The SQLWhisperer team takes security seriously. Because this project translates natural language to executable SQL queries, security guardrails against destructive execution, prompt injection, and unauthorized data extraction are core priorities.

If you believe you have found a security vulnerability (such as a bypass to SQL execution guardrails or unintended database writes):

1. **Do not open a public GitHub issue.**
2. Send an email describing the vulnerability, affected components, and reproduction steps to the project maintainers.
3. You will receive an acknowledgment within 48 hours.
4. We will coordinate a fix and release a patched version before public disclosure.

## Security Design Principles

- **Read-Only by Default**: SQL execution is restricted to `SELECT` operations only.
- **Regex & AST Guardrails**: Destructive commands (`DROP`, `DELETE`, `ALTER`, `TRUNCATE`, etc.) are intercepted before reaching the database connector.
- **Table Blocklist**: Sensitive system tables and blocked tables configured via `BLOCKED_TABLES` are stripped from schema introspection and execution.
- **Query Timeout**: All queries run with bounded execution timeouts (`QUERY_TIMEOUT_SECONDS`) to avoid denial of service.
