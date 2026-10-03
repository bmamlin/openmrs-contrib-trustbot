"""Pydantic data models for the rules engine.

Represents the shape of `rules.yaml` (see openspec/specs/config-schema.md)
as typed objects: a Rule has one or more Triggers and one or more Actions.
Trigger/action `type` fields are open-ended strings (not enums) so that new
trigger/action types can be registered without changing these models —
see src/triggers/ and src/actions/ for the registries that map a `type`
string to its handler.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Trigger(BaseModel):
    """A single trigger condition within a rule (e.g. webhook, workflow)."""

    model_config = ConfigDict(extra="allow")

    type: str
    # Trigger-specific parameters (e.g. `name`, `channel`) are captured
    # via pydantic's extra-fields support rather than a rigid schema, since
    # each trigger type defines its own parameters.


class Action(BaseModel):
    """A single action to execute when a rule fires (e.g. keycloak_add_groups)."""

    model_config = ConfigDict(extra="allow")

    type: str
    # Action-specific parameters (e.g. `groups`) are captured via
    # pydantic's extra-fields support.


class Rule(BaseModel):
    """A single rule: named, toggleable, with triggers (OR logic) and actions."""

    name: str
    enabled: bool = True
    triggers: list[Trigger]
    actions: list[Action]


class RuleSet(BaseModel):
    """The full parsed contents of rules.yaml."""

    rules: list[Rule]


class TriggerEvent(BaseModel):
    """A trigger event handed to the engine by an API/integration layer.

    Constructed only after that layer's own authorization checks pass
    (e.g. Slack signature + channel restriction) — the engine and
    trigger matchers never see raw external payloads, only this envelope.
    """

    type: str                    # matches a Trigger.type, e.g. "slack_trust_command"
    name: str | None = None      # matches a Trigger.name, e.g. "trusted" or "user_promoted"
    openmrs_id: str              # target user
    source: str | None = None    # e.g. the issuing Slack username
    payload: dict[str, Any] = {}


class ActionResult(BaseModel):
    """The outcome of executing one action, used for both the caller's
    response and the audit log entry."""

    status: Literal["success", "no_change", "failure", "dry_run"]
    detail: str | None = None
    action_detail: str | None = None   # e.g. JSON list of groups actually added
