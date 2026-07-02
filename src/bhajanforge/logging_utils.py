"""Structured logging for BhajanForge.

Never logs secrets (R7.1). Provides per-stage timing helpers.
"""

from __future__ import annotations

import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Iterator

_SECRET_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password)\s*[=:]\s*\S+", re.IGNORECASE
)


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts anything resembling a secret."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return _SECRET_PATTERN.sub(r"\1=***REDACTED***", msg)


def get_logger(name: str = "bhajanforge") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


@contextmanager
def stage_timer(logger: logging.Logger, stage: str) -> Iterator[dict]:
    """Time a pipeline stage; yields a dict that receives {'elapsed_sec': ...}."""
    timing: dict = {}
    start = time.perf_counter()
    logger.info("stage '%s' started", stage)
    try:
        yield timing
    finally:
        elapsed = round(time.perf_counter() - start, 3)
        timing["elapsed_sec"] = elapsed
        logger.info("stage '%s' finished in %ss", stage, elapsed)
