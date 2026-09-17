"""The `discourse_trust_level` trigger.

Matches when a Discourse trust-level-change webhook event reports a trust
level at or above the rule's configured `threshold` (0-4). Per
openspec/specs/config-schema.md, firing on every event at or above
threshold (rather than only on the exact transition) is intentional and
safe because keycloak_add_groups is idempotent.
"""

from __future__ import annotations

from typing import Any

from src.engine.models import Trigger


def matches(trigger: Trigger, event: Any) -> bool:
    """Return True if a discourse_trust_level trigger matches the given event."""
    raise NotImplementedError
