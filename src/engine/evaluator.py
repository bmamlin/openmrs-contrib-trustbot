"""Rule evaluation logic.

Given an incoming trigger event (e.g. a Discourse trust-level change or a
Slack /trust command) and the current RuleSet, determines which rules
match (any of a rule's triggers matching is sufficient — OR logic per
openspec/specs/config-schema.md) and executes each matched rule's actions
via the action registry in src/actions/.

The engine itself must stay generic: it dispatches to trigger matchers
(src/triggers/) and action executors (src/actions/) by `type` string, so
that adding a new trigger or action type requires no changes here.
"""

from __future__ import annotations

from typing import Any

from src.engine.models import Rule, RuleSet


def evaluate(rule_set: RuleSet, event: Any) -> list[Rule]:
    """Return the list of rules whose triggers match the given event.

    Only `enabled` rules are considered.
    """
    raise NotImplementedError


def execute_rule(rule: Rule, event: Any) -> None:
    """Execute all actions for a matched rule and record the outcome to the audit log.

    All actions must be idempotent; a no-op result (e.g. user already has
    the group) is still recorded in the audit log per spec §4.4.
    """
    raise NotImplementedError
