"""
utils/logger.py
---------------
Structured JSON logger for the DocuIntel backend.

Why JSON logging?
  - Machine-readable (easy to parse/search in log aggregators)
  - Every log line has consistent fields: timestamp, level, module, message
  - Extra context (latency, filename, chunk counts) can be attached per-call

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Chunks stored", extra={"count": 42, "filename": "report.pdf"})
"""

import logging
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.
    Any key=value pairs passed via `extra={}` are merged into the log line.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "func": record.funcName,
            "message": record.getMessage(),
        }

        # Attach any extra fields passed by the caller
        # Standard LogRecord attributes we want to skip
        _skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _skip:
                log_data[key] = value

        # Attach exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Returns a named logger with JSON formatting.
    Multiple calls with the same name return the same logger (Python default).
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # Import here to avoid circular imports
    from config import settings
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Don't propagate to root logger (avoids duplicate output)
    logger.propagate = False

    return logger


class Timer:
    """
    Simple context manager for timing code blocks.

    Usage:
        with Timer() as t:
            do_something()
        logger.info("Done", extra={"elapsed_ms": t.elapsed_ms})
    """

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self._end = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        """Returns the elapsed time in milliseconds."""
        if not hasattr(self, "_end"):
            return 0.0
        return (self._end - self._start) * 1000
