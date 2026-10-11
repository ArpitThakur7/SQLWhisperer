# Contributing to SQLWhisperer 🔮

Thank you for your interest in contributing to SQLWhisperer! We welcome contributions from developers, data engineers, and AI practitioners of all skill levels.

---

## 🚀 Getting Started

### 1. Fork and Clone
```bash
git clone https://github.com/your-username/sqlwhisperer.git
cd sqlwhisperer
```

### 2. Set Up a Virtual Environment
```bash
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -e ".[dev]"
```

### 4. Configure Environment
```bash
cp .env.example .env    # On Windows: copy .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

---

## 🧪 Running Tests & Quality Checks

Before submitting a pull request, ensure all tests and lint checks pass:

```bash
# Run test suite
pytest tests/ -v

# Run linting check
ruff check .

# Check project health dashboard
python -m scripts.project_tracker
```

---

## 🌿 Branching & Pull Requests

1. **Branch Naming**:
   - `feat/feature-name` (e.g. `feat/ollama-support`)
   - `fix/bug-description` (e.g. `fix/sql-regex-bypass`)
   - `docs/documentation-update` (e.g. `docs/setup-guide`)

2. **Commit Convention**:
   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add support for DuckDB dialect`
   - `fix: prevent table hallucination in schema retriever`
   - `docs: improve quickstart instructions`
   - `test: add AST security unit tests`

3. **Submitting PRs**:
   - Open a PR against the `main` branch.
   - Fill out the PR template with context, changes made, and test output.
   - Link any related issues (e.g., `Closes #12`).

---

## 💡 Code Style & Standards

- **Python 3.10+**: Use modern type hinting (`list[str]`, `dict[str, Any]`, `X | None`).
- **Pydantic Models**: Keep schemas in `src/schemas/` with clear validation rules.
- **LCEL Chains**: Keep chains composable and decoupled in `src/chains/`.
- **Database Safety**: Never execute DML/DDL queries directly. Always pass queries through the validation and executor chains.
