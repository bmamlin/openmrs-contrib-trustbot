"""The `slack_trust_command` and `slack_revoke_command` triggers.

Match Slack `/trust <openmrs-id>` and `/revoke <openmrs-id>` slash command
events issued from the configured designated private channel
(`slack.trusted_channel_id` in config.yaml). Commands from any other
channel must never match (see openspec/specs/overview.md §6.1) — that
check belongs here, not further downstream.
"""

from __future__ import annotations

from typing import Any

from src.engine.models import Trigger


def matches_trust(trigger: Trigger, event: Any) -> bool:
    """Return True if a slack_trust_command trigger matches the given event."""
    raise NotImplementedError


def matches_revoke(trigger: Trigger, event: Any) -> bool:
    """Return True if a slack_revoke_command trigger matches the given event."""
    raise NotImplementedError
