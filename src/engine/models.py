"""Pydantic data models for the rules engine.

Represents the shape of `rules.yaml` (see openspec/specs/config-schema.md)
as typed objects: a Rule has one or more Triggers and one or more Actions.
Trigger/action `type` fields are open-ended strings (not enums) so that new
trigger/action types can be registered without changing these models —
see src/triggers/ and src/actions/ for the registries that map a `type`
string to its handler.
"""

from __future__ import annotations

from pydantic import BaseModel


class Trigger(BaseModel):
    """A single trigger condition within a rule (e.g. discourse_trust_level)."""

    type: str
    # Trigger-specific parameters (e.g. `threshold`, `channel`) are captured
    # via pydantic's extra-fields support rather than a rigid schema, since
    # each trigger type defines its own parameters.

    class Config:
        extra = "allow"


class Action(BaseModel):
    """A single action to execute when a rule fires (e.g. keycloak_add_groups)."""

    type: str
    # Action-specific parameters (e.g. `groups`) are captured via
    # pydantic's extra-fields support.

    class Config:
        extra = "allow"


class Rule(BaseModel):
    """A single rule: named, toggleable, with triggers (OR logic) and actions."""

    name: str
    enabled: bool = True
    triggers: list[Trigger]
    actions: list[Action]


class RuleSet(BaseModel):
    """The full parsed contents of rules.yaml."""

    rules: list[Rule]
