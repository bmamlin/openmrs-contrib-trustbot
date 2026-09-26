"""Slack client/app setup (built on slack-bolt).

Registers the `/trust`, `/revoke`, and `/trust-status` slash commands and
relies on slack-bolt's own signature verification (SLACK_SIGNING_SECRET,
checked by the App/SlackRequestHandler before any listener runs — see the
add-slack-trust-grant design.md) and posting responses back to Slack
(SLACK_BOT_TOKEN). `/trust` and `/revoke`'s channel-restriction enforcement
and TriggerEvent construction live in src/triggers/slack.py; rule loading
and dispatch live in src/engine/loader.py and src/engine/evaluator.py.
`/trust-status` is read-only and never reaches the rules engine — see its
own handler below and the add-slack-trust-status-command design.md for why
its channel check is inline here rather than routed through
src/triggers/slack.py. This module wires all three together behind their
command listeners.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Sequence

from slack_bolt import App

from src.audit.db import get_recent_events
from src.engine import evaluator
from src.engine.loader import load_rules
from src.engine.models import ActionResult
from src.integrations import discourse as discourse_integration
from src.integrations import keycloak as keycloak_integration
from src.integrations.keycloak import UserNotFoundError
from src.triggers.slack import build_revoke_event, build_trust_event


@dataclass
class SlackContext:
    """Per-app-instance context the `/trust` handler needs beyond the Slack payload itself."""

    trusted_channel_id: str
    audit_conn: sqlite3.Connection


def create_slack_app(
    bot_token: str,
    signing_secret: str,
    *,
    trusted_channel_id: str,
    audit_conn: sqlite3.Connection,
) -> App:
    """Construct and return the configured slack_bolt App with the `/trust` command registered."""
    # token_verification_enabled=False: skip the eager `auth.test` network
    # call slack-bolt otherwise makes at construction time. Per-request
    # signature verification (the actual security control) still happens
    # via signing_secret on every incoming request. Disabling this means
    # the service can start without live Slack connectivity/credentials
    # (e.g. local dev, or Slack being briefly unreachable at boot).
    app = App(token=bot_token, signing_secret=signing_secret, token_verification_enabled=False)
    context = SlackContext(trusted_channel_id=trusted_channel_id, audit_conn=audit_conn)

    @app.command("/trust")
    def handle_trust_command(ack, command, respond) -> None:
        # Ack immediately: Slack requires a response within 3 seconds, and
        # per the "silent rejection" design decision this ack (with no
        # text) is what satisfies that for an unauthorized-channel command
        # without showing the channel anything.
        ack()
        _handle_trust(command, context, respond)

    @app.command("/revoke")
    def handle_revoke_command(ack, command, respond) -> None:
        ack()  # same silent-rejection rationale as /trust, see above
        _handle_revoke(command, context, respond)

    @app.command("/trust-status")
    def handle_trust_status_command(ack, command, respond) -> None:
        ack()  # same silent-rejection rationale as /trust, see above
        _handle_trust_status(command, context, respond)

    return app


def _handle_trust(command: dict, context: SlackContext, respond) -> None:
    event = build_trust_event(command, trusted_channel_id=context.trusted_channel_id)
    if event is None:
        return  # wrong channel: silent rejection, no response (see build_trust_event)

    if not event.openmrs_id:
        respond("Usage: `/trust <openmrs-id>`")
        return

    rule_set = load_rules()
    matched_rules = evaluator.evaluate(rule_set, event)

    if not matched_rules:
        respond(f"No rule is configured to handle `/trust` for `{event.openmrs_id}`.")
        return

    outcomes: list[ActionResult] = []
    for rule in matched_rules:
        outcomes.extend(evaluator.execute_rule(rule, event, conn=context.audit_conn))

    respond(_format_response(event.openmrs_id, outcomes))


def _format_response(openmrs_id: str, outcomes: Sequence[ActionResult]) -> str:
    failures = [o for o in outcomes if o.status == "failure"]
    if failures:
        return f"Could not grant access to `{openmrs_id}`: {failures[0].detail}"

    if all(o.status == "no_change" for o in outcomes):
        return f"`{openmrs_id}` is already trusted."

    return f"`{openmrs_id}` has been granted community edit access."


def _handle_revoke(command: dict, context: SlackContext, respond) -> None:
    event = build_revoke_event(command, trusted_channel_id=context.trusted_channel_id)
    if event is None:
        return  # wrong channel: silent rejection, no response (see build_revoke_event)

    if not event.openmrs_id:
        respond("Usage: `/revoke <openmrs-id>`")
        return

    rule_set = load_rules()
    matched_rules = evaluator.evaluate(rule_set, event)

    if not matched_rules:
        respond(f"No rule is configured to handle `/revoke` for `{event.openmrs_id}`.")
        return

    outcomes: list[ActionResult] = []
    for rule in matched_rules:
        outcomes.extend(evaluator.execute_rule(rule, event, conn=context.audit_conn))

    respond(_format_revoke_response(event.openmrs_id, outcomes))


def _format_revoke_response(openmrs_id: str, outcomes: Sequence[ActionResult]) -> str:
    failures = [o for o in outcomes if o.status == "failure"]
    if failures:
        return f"Could not revoke access for `{openmrs_id}`: {failures[0].detail}"

    if all(o.status == "no_change" for o in outcomes):
        return f"`{openmrs_id}` is already not trusted."

    return f"`{openmrs_id}` has had community edit access revoked."


def _handle_trust_status(command: dict, context: SlackContext, respond) -> None:
    # No TriggerEvent here (unlike /trust and /revoke): this command never
    # reaches the rules engine, so the channel check is done inline rather
    # than through src/triggers/slack.py's build_*_event() — see design.md.
    if command.get("channel_id") != context.trusted_channel_id:
        return  # wrong channel: silent rejection, no response

    openmrs_id = (command.get("text") or "").strip()
    if not openmrs_id:
        respond("Usage: `/trust-status <openmrs-id>`")
        return

    groups: list[str] | None
    groups_error: str | None
    try:
        groups = keycloak_integration.get_client().get_user_groups(openmrs_id)
        groups_error = None
    except UserNotFoundError:
        respond(f"`{openmrs_id}` was not found in Keycloak.")
        return
    except Exception as exc:  # noqa: BLE001 - degrade this section, see design.md
        groups = None
        groups_error = str(exc)

    trust_level: int | None
    trust_level_error: str | None
    try:
        trust_level = discourse_integration.get_client().get_trust_level(openmrs_id)
        trust_level_error = None
    except Exception as exc:  # noqa: BLE001 - degrade this section, see design.md
        trust_level = None
        trust_level_error = str(exc)

    recent_events: list[dict] | None
    events_error: str | None
    try:
        recent_events = get_recent_events(context.audit_conn, openmrs_id, limit=5)
        events_error = None
    except Exception as exc:  # noqa: BLE001 - degrade this section, see design.md
        recent_events = None
        events_error = str(exc)

    respond(
        _format_trust_status_response(
            openmrs_id,
            groups=groups,
            groups_error=groups_error,
            trust_level=trust_level,
            trust_level_error=trust_level_error,
            recent_events=recent_events,
            events_error=events_error,
        )
    )


def _format_trust_status_response(
    openmrs_id: str,
    *,
    groups: list[str] | None,
    groups_error: str | None,
    trust_level: int | None,
    trust_level_error: str | None,
    recent_events: list[dict] | None,
    events_error: str | None,
) -> str:
    lines = [f"*Trust status for* `{openmrs_id}`"]

    if groups_error is not None:
        lines.append(f"- Keycloak groups: unavailable ({groups_error})")
    else:
        lines.append(f"- Keycloak groups: {', '.join(groups) if groups else '(none)'}")

    if trust_level_error is not None:
        lines.append(f"- Discourse trust level: unavailable ({trust_level_error})")
    else:
        lines.append(f"- Discourse trust level: {trust_level}")

    if events_error is not None:
        lines.append(f"- Recent audit history: unavailable ({events_error})")
    elif not recent_events:
        lines.append("- Recent audit history: (none)")
    else:
        lines.append("- Recent audit history:")
        for event in recent_events:
            lines.append(
                f"   - {event['timestamp']}: {event['action']} via "
                f"{event['trigger']} -> {event['status']}"
            )

    return "\n".join(lines)
