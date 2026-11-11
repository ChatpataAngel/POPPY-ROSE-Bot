"""Secure, consistent logging for POPPY ROSE.

All console records pass through a redacting formatter. HTTP client success
logs are reduced to WARNING so Telegram API URLs (which contain the bot token)
are not printed during normal operation. Redaction is still applied to every
record, including exception tracebacks and third-party logger messages.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time


_REDACTION_RULES = (
    # Telegram Bot API token, including the `bot` prefix used in request URLs.
    (re.compile(r"(?i)\b(?:bot)?\d{6,}:[A-Za-z0-9_-]{20,}\b"), "[REDACTED_TELEGRAM_BOT_TOKEN]"),
    # Database connection strings can contain usernames/passwords and hosts.
    (re.compile(r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://[^\s\"'<>]+"), "[REDACTED_DATABASE_URI]"),
    # Common bearer credentials.
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    # Secret-like key/value pairs, including JSON and .env-style log messages.
    (
        re.compile(
            r"(?i)(\b[A-Z0-9_]*(?:BOT[_-]?TOKEN|TOKEN|SECRET|PASSWORD|PASSWD|"
            r"API[_-]?KEY|ACCESS[_-]?KEY|DATABASE[_-]?URL|MONGO(?:DB)?[_-]?URI|"
            r"PRIVATE[_-]?KEY|AUTHORIZATION)[A-Z0-9_]*\b\s*[\"']?\s*[:=]\s*)"
            r"[\"']?[^\s,;\"'}\]]+"
        ),
        r"\1[REDACTED]",
    ),
    # Recognizable provider tokens even when a caller logs them without a key.
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED_ACCESS_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
)


def redact_secrets(value: object) -> str:
    """Return a string with common credentials and connection strings masked."""
    try:
        result = str(value)
    except Exception:
        result = "<unprintable value>"
    for pattern, replacement in _REDACTION_RULES:
        result = pattern.sub(replacement, result)
    return result


class RedactingFormatter(logging.Formatter):
    """Apply redaction after formatting so messages, arguments and tracebacks are covered."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def configure_logging() -> None:
    """Install one redacting stdout handler and tune noisy dependency loggers."""
    root = logging.getLogger()
    if getattr(root, "_poppy_secure_logging_configured", False):
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    level = getattr(logging, level_name, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        RedactingFormatter(
            fmt="%(asctime)s.%(msecs)03dZ | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.formatter.converter = time.gmtime

    # Replace inherited/default handlers to ensure console output is redacted.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Successful Telegram HTTP calls include the bot token in their URL.
    # Keep these request lines out of Render logs; warnings/errors still pass
    # through the redacting root formatter.
    for name in ("httpx", "httpcore", "telegram.request", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.captureWarnings(True)
    root._poppy_secure_logging_configured = True

    logging.getLogger("poppy_rose").info(
        "Secure logging initialized | level=%s | format=REDACTED_CONSOLE",
        level_name,
    )
