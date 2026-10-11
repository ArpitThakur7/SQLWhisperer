"""Unit tests for the Semantic Business Glossary."""

from src.semantic.glossary import SemanticGlossary


def test_semantic_glossary_loading():
    """Verify glossary loads metrics, synonyms, and rules."""
    glossary = SemanticGlossary()
    assert "metrics" in glossary.data
    assert "active_customer" in glossary.data["metrics"]
    assert "synonyms" in glossary.data
    assert "rules" in glossary.data


def test_semantic_context_matching():
    """Verify question matching extracts relevant metric guidance."""
    glossary = SemanticGlossary()

    # Query with metric keyword
    context = glossary.get_context("Show me all active customers in the US")
    assert "Active Customer" in context
    assert "90 days" in context

    # Query with synonym keyword
    context_syn = glossary.get_context("Who are the top buyers by spend?")
    assert "buyers" in context_syn
    assert "customers" in context_syn

    # Query with revenue
    context_rev = glossary.get_context("What is our total revenue this month?")
    assert "Revenue" in context_rev
