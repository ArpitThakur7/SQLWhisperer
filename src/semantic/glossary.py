"""Semantic Business Glossary Loader and Context Matcher.

Extracts business metric formulas, column synonyms, and organizational rules
from config/glossary.yaml and dynamically injects relevant context into the Text2SQL prompt.
"""

from pathlib import Path
from typing import Any
import yaml
from loguru import logger

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_GLOSSARY_PATH = ROOT_DIR / "config" / "glossary.yaml"


class SemanticGlossary:
    """Manages loading and contextual retrieval of business definitions."""

    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_GLOSSARY_PATH
        self.data: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load glossary YAML file."""
        if not self.config_path.is_file():
            logger.debug(f"No glossary file found at {self.config_path}")
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}
            logger.debug(f"Loaded semantic glossary with {len(self.data.get('metrics', {}))} metrics")
        except Exception as exc:
            logger.warning(f"Failed to parse glossary at {self.config_path}: {exc}")
            self.data = {}

    def get_context(self, question: str) -> str:
        """Find matching metrics, synonyms, and rules relevant to the question."""
        if not self.data:
            return ""

        q_lower = question.lower()
        matched_metrics: list[str] = []
        matched_synonyms: list[str] = []

        # 1. Match Metrics
        metrics = self.data.get("metrics", {})
        for metric_name, details in metrics.items():
            readable_name = metric_name.replace("_", " ")
            if readable_name in q_lower or metric_name in q_lower:
                guidance = details.get("guidance", details.get("description", ""))
                matched_metrics.append(f"- **{readable_name.title()}**: {guidance}")

        # 2. Match Synonyms
        synonyms = self.data.get("synonyms", {})
        for term, target in synonyms.items():
            if term in q_lower:
                matched_synonyms.append(f"- \"{term}\" refers to entity/table `{target}`")

        # 3. Rules
        rules = self.data.get("rules", [])

        # If nothing matched and no general rules, return empty
        if not matched_metrics and not matched_synonyms and not rules:
            return ""

        lines = ["\nBUSINESS GLOSSARY & DOMAIN RULES:"]
        if matched_metrics:
            lines.append("Relevant Business Metrics:")
            lines.extend(matched_metrics)
        if matched_synonyms:
            lines.append("Vocabulary / Synonyms:")
            lines.extend(matched_synonyms)
        if rules:
            lines.append("Domain Guidelines:")
            for rule in rules:
                lines.append(f"- {rule}")

        return "\n".join(lines) + "\n"
