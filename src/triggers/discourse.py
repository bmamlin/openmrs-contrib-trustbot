"""The `discourse_trust_level` trigger.

Matches when a Discourse trust-level-change webhook event reports a trust
level at or above the rule's configured `threshold` (0-4). Per
openspec/specs/config-schema.md, firing on every event at or above
threshold (rather than only on the exact transition) is intentional and
safe because keycloak_add_groups is idempotent.

The event itself is delivered via a Discourse Workflow's HTTP action
(see src/api/webhooks.py and the add-discourse-trust-level-trigger
design.md) — this module only matches/builds TriggerEvents, it never
touches the request/signature/replay-window verification that happens
before a TriggerEvent exists.
"""

from __future__ import annotations

from src.engine.models import Trigger, TriggerEvent


def matches(trigger: Trigger, event: TriggerEvent) -> bool:
    """Return True if a discourse_trust_level trigger matches the given event."""
    return (
        trigger.type == "discourse_trust_level"
        and event.type == "discourse_trust_level"
        and event.payload.get("new_trust_level", -1) >= trigger.threshold
    )


def build_trust_level_event(payload: dict, *, discourse_base_url: str) -> TriggerEvent:
    """Build a discourse_trust_level TriggerEvent from an already-verified,
    already-parsed webhook payload (see src/api/webhooks.py).

    `source` is the configured Discourse instance URL — there's no
    per-request issuer the way Slack commands have an issuing username
    (see design.md), and this matches the audit schema's own
    `trigger_src` example ("Discourse webhook URL").
    """
    return TriggerEvent(
        type="discourse_trust_level",
        openmrs_id=payload["username"],
        source=discourse_base_url,
        payload={
            "old_trust_level": payload["old_trust_level"],
            "new_trust_level": payload["new_trust_level"],
        },
    )
