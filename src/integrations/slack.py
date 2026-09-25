"""Slack client/app setup (built on slack-bolt).

Registers the `/trust` and `/revoke` slash commands (`/trust-status` is
out of scope for this change) and relies on slack-bolt's own signature
verification (SLACK_SIGNING_SECRET, checked by the App/SlackRequestHandler
before any listener runs — see the add-slack-trust-grant design.md) and
posting responses back to Slack (SLACK_BOT_TOKEN). Channel-restriction
enforcement and TriggerEvent construction live in src/triggers/slack.py;
rule loading and dispatch live in src/engine/loader.py and
src/engine/evaluator.py. This module wires those together behind the
`/trust` and `/revoke` command listeners.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Sequence

from slack_bolt import App

from src.engine import evaluator
from src.engine.loader import load_rules
from src.engine.models import ActionResult
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
