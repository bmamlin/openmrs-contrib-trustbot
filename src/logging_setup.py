"""Minimal application logging setup.

Per openspec/specs/overview.md section 5.5, logs must be structured JSON
to stdout, and the level must be configurable via LOG_LEVEL at startup
and at runtime via the admin API (see src/api/admin.py: create_admin_router,
which calls set_log_level() below).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}

# Header/body field names that must never appear in a DEBUG log, even
# though DEBUG is otherwise meant to dump request headers/bodies freely.
# Header names are matched case-insensitively (HTTP header names are
# case-insensitive); Slack body keys are matched exactly (they're
# programmatic field names, not HTTP headers).
REDACTED_HEADER_NAMES = {"authorization"}
REDACTED_SLACK_BODY_FIELDS = {"token"}


class JsonFormatter(logging.Formatter):
    """Renders a LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of `headers` with any REDACTED_HEADER_NAMES value replaced.

    Does not mutate `headers`. Matches header names case-insensitively.
    """
    return {
        key: ("[REDACTED]" if key.lower() in REDACTED_HEADER_NAMES else value)
        for key, value in headers.items()
    }


def redact_slack_body(body: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of `body` with any REDACTED_SLACK_BODY_FIELDS value replaced.

    Does not mutate `body`.
    """
    return {
        key: ("[REDACTED]" if key in REDACTED_SLACK_BODY_FIELDS else value)
        for key, value in body.items()
    }


def set_log_level(level: str) -> None:
    """Change the root logger's level immediately. Raises ValueError if unrecognized."""
    normalized = level.upper()
    if normalized not in VALID_LOG_LEVELS:
        raise ValueError(f"unrecognized log level: {level!r}")
    logging.getLogger().setLevel(normalized)


def configure_logging(default_level: str = "INFO") -> None:
    """Configure the root logger: JSON to stdout, level from LOG_LEVEL or default_level.

    A blank (but present) LOG_LEVEL is treated the same as unset, falling
    back to default_level — mirroring the DISCOURSE_REPLAY_WINDOW_SECONDS
    fix in src/main.py for the same `dotenv run`-exports-blank-keys
    footgun.
    """
    level_override = os.environ.get("LOG_LEVEL", "").strip()
    level = (level_override or default_level).upper()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    set_log_level(level)
