"""The `slack_trust_command` and `slack_revoke_command` triggers.

Match Slack `/trust <openmrs-id>` and `/revoke <openmrs-id>` slash command
events issued from the configured designated private channel
(`slack.trusted_channel_id` in config.yaml). Commands from any other
channel must never match (see openspec/specs/overview.md §6.1) — that
check belongs here, not further downstream.
"""

from __future__ import annotations

from src.engine.models import Trigger, TriggerEvent


def matches_trust(trigger: Trigger, event: TriggerEvent) -> bool:
    """Return True if a slack_trust_command trigger matches the given event.

    The MVP schema has no extra per-rule fields on this trigger (channel
    restriction is a single global setting, enforced in
    build_trust_event() below, before a TriggerEvent ever exists) so this
    is just a type check.
    """
    return trigger.type == "slack_trust_command" and event.type == "slack_trust_command"


def matches_revoke(trigger: Trigger, event: TriggerEvent) -> bool:
    """Return True if a slack_revoke_command trigger matches the given event.

    Mirrors matches_trust(): no extra per-rule fields on this trigger in
    the MVP schema, so this is just a type check.
    """
    return trigger.type == "slack_revoke_command" and event.type == "slack_revoke_command"


def build_trust_event(command: dict, *, trusted_channel_id: str) -> TriggerEvent | None:
    """Build a slack_trust_command TriggerEvent from a Slack `/trust` command payload.

    `command` is the slack-bolt command payload (has `channel_id`, `text`,
    `user_name`, ...). Returns None if the command was issued outside the
    configured trusted channel — per the slack-trust-command spec, this is
    a silent rejection: no event, no rule evaluation, no response.
    """
    if command.get("channel_id") != trusted_channel_id:
        return None

    openmrs_id = (command.get("text") or "").strip()
    return TriggerEvent(
        type="slack_trust_command",
        openmrs_id=openmrs_id,
        source=command.get("user_name"),
        payload={"channel_id": command.get("channel_id")},
    )


def build_revoke_event(command: dict, *, trusted_channel_id: str) -> TriggerEvent | None:
    """Build a slack_revoke_command TriggerEvent from a Slack `/revoke` command payload.

    Mirrors build_trust_event(): same channel-restriction check, same
    silent-rejection behavior for commands from outside the trusted
    channel.
    """
    if command.get("channel_id") != trusted_channel_id:
        return None

    openmrs_id = (command.get("text") or "").strip()
    return TriggerEvent(
        type="slack_revoke_command",
        openmrs_id=openmrs_id,
        source=command.get("user_name"),
        payload={"channel_id": command.get("channel_id")},
    )
