"""Security regression tests for console and diagnostic error redaction."""
from __future__ import annotations

import logging

from src.utils.logging_config import RedactingFormatter, redact_secrets


def test_redacts_telegram_token_in_api_url():
    token = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    text = f"POST https://api.telegram.org/bot{token}/getUpdates"
    cleaned = redact_secrets(text)
    assert token not in cleaned
    assert "REDACTED_TELEGRAM_BOT_TOKEN" in cleaned


def test_redacts_database_uri_and_secret_assignments():
    mongo = "mongodb+srv://angel:verySecretPassword@cluster.example/db"
    cleaned = redact_secrets(f"MONGO_DB_URI={mongo} API_KEY=superSecretKey")
    assert mongo not in cleaned
    assert "verySecretPassword" not in cleaned
    assert "superSecretKey" not in cleaned
    assert "REDACTED" in cleaned


def test_redacts_bearer_header():
    bearer = "Bearer eyJhbGciOiJIUzI1NiJ9.very.secret.value"
    cleaned = redact_secrets(bearer)
    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "Bearer [REDACTED]" in cleaned


def test_formatter_redacts_exception_traceback_text():
    token = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    try:
        raise RuntimeError(f"request failed at https://api.telegram.org/bot{token}/getMe")
    except RuntimeError:
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="request failed", args=(), exc_info=__import__("sys").exc_info(),
        )
    output = RedactingFormatter("%(message)s").format(record)
    assert token not in output
    assert "REDACTED_TELEGRAM_BOT_TOKEN" in output
