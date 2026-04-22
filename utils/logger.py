"""
SENTINEL — Structured Logging
Provides a consistent logger for all system components.
"""

import logging
import sys
from config import LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """Create a structured logger with consistent formatting."""
    logger = logging.getLogger(f"sentinel.{name}")

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s │ %(levelname)-7s │ %(name)-30s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    return logger
