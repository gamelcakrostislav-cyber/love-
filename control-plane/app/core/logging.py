"""Minimal structured logging setup shared by all processes."""

from __future__ import annotations

import logging

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
