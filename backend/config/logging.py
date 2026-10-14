"""JSON logging: formatter, context filter and redaction filter (docs/spec.md S16)."""

import logging
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger.json import JsonFormatter

CONTEXT_FIELDS = ("run_id", "video_id", "node")
_context: dict[str, ContextVar[str | None]] = {
    name: ContextVar(name, default=None) for name in CONTEXT_FIELDS
}

REDACTED = "[REDACTED]"
SECRET_SUFFIXES = ("_KEY", "_SECRET", "_PASSWORD")
SECRET_PATTERNS = (
    r"AIza[0-9A-Za-z_-]{20,}",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"Bearer \S+",
)
# Shorter env values (e.g. the local-only POSTGRES_PASSWORD=app) would also match ordinary
# words like "application", so only values of this length or more are redacted.
MIN_SECRET_LENGTH = 8


@contextmanager
def log_context(**values: str) -> Iterator[None]:
    """Add run_id, video_id and/or node to every log record inside the block."""
    tokens = [(_context[name], _context[name].set(value)) for name, value in values.items()]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


class ContextFilter(logging.Filter):
    """Copy the context values that are set onto the record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, var in _context.items():
            value = var.get()
            if value is not None:
                setattr(record, name, value)
        return True


def secret_values(environ: Mapping[str, str] | None = None) -> list[str]:
    environ = os.environ if environ is None else environ
    return [
        value
        for name, value in environ.items()
        if name.upper().endswith(SECRET_SUFFIXES) and len(value) >= MIN_SECRET_LENGTH
    ]


class RedactionFilter(logging.Filter):
    """Replace secret env values and known key/token patterns with [REDACTED].

    The message is rendered with its arguments first, so a secret passed as an argument is
    redacted too. Tracebacks are rendered and redacted the same way.
    """

    def __init__(self, name: str = "", environ: Mapping[str, str] | None = None) -> None:
        super().__init__(name)
        literals = [re.escape(v) for v in sorted(secret_values(environ), key=len, reverse=True)]
        self.pattern = re.compile("|".join([*literals, *SECRET_PATTERNS]))

    def redact(self, text: str) -> str:
        return self.pattern.sub(REDACTED, text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = None
        if record.exc_info:
            text = logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
            record.exc_text = self.redact(text)
        elif record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


class JsonLogFormatter(JsonFormatter):
    """One JSON object per line: timestamp, level, logger, message (+ context, exc_info)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("fmt", "%(asctime)s %(levelname)s %(name)s %(message)s")
        kwargs.setdefault(
            "rename_fields", {"asctime": "timestamp", "levelname": "level", "name": "logger"}
        )
        super().__init__(*args, **kwargs)


def logging_config(level: str) -> dict[str, Any]:
    """The LOGGING dict: one stdout handler with both filters, shared by Django and Celery."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": ContextFilter},
            "redact": {"()": RedactionFilter},
        },
        "formatters": {"json": {"()": JsonLogFormatter}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
                "filters": ["context", "redact"],
            }
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            # Replace Django's default handlers (plain text) with the JSON one.
            "django": {"handlers": ["console"], "level": level, "propagate": False},
        },
    }
