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

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


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
