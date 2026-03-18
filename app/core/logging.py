"""Structured logging configuration for the application."""

import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure root logger with a structured, human-readable format.

    Sets the log level from application settings and directs all output
    to stdout so container log collectors can pick it up.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    # Silence overly verbose third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
