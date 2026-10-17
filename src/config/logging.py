"""Loguru-based structured logging configuration."""

import sys
from loguru import logger


def setup_logging(level: str = "INFO") -> None:
    """Configure Loguru with console + file outputs.

    Console gets human-readable coloured output.
    File gets JSON-serialized records for machine analysis.
    """
    logger.remove()  # Remove default handler

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Console: human-readable, coloured
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
    )

    # File: structured JSON for analysis
    logger.add(
        "logs/sqlwhisperer_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DDTHH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        rotation="50 MB",
        retention="30 days",
        level="DEBUG",
        serialize=True,
    )
