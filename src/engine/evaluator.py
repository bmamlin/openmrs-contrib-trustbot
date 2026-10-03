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

import logging
import sqlite3
from typing import Callable

from src.audit.db import record_event
from src.engine.models import Action, ActionResult, Rule, RuleSet, Trigger, TriggerEvent

logger = logging.getLogger(__name__)

TRIGGER_MATCHERS: dict[str, Callable[[Trigger, TriggerEvent], bool]] = {}
ACTION_EXECUTORS: dict[str, Callable[[Action, TriggerEvent, bool], ActionResult]] = {}


def register_trigger(type_name: str, matcher: Callable[[Trigger, TriggerEvent], bool]) -> None:
    TRIGGER_MATCHERS[type_name] = matcher


def register_action(
    type_name: str, executor: Callable[[Action, TriggerEvent, bool], ActionResult]
) -> None:
    ACTION_EXECUTORS[type_name] = executor


def _trigger_matches(trigger: Trigger, event: TriggerEvent) -> bool:
    if trigger.type != event.type:
        return False
    matcher = TRIGGER_MATCHERS.get(trigger.type)
    if matcher is None:
        # Trigger type is known to rules.yaml's schema but not (yet)
        # registered with an implementation — never matches, rather than
        # erroring, so unimplemented trigger types can coexist in
        # rules.yaml with implemented ones.
        return False
    return matcher(trigger, event)


def evaluate(rule_set: RuleSet, event: TriggerEvent) -> list[Rule]:
    """Return the list of rules whose triggers match the given event.

    Only `enabled` rules are considered. A rule matches if ANY of its
    triggers matches (OR logic).
    """
    logger.debug(
        "evaluating event: type=%s name=%s openmrs_id=%s payload=%s",
        event.type,
        event.name,
        event.openmrs_id,
        event.payload,
    )

    matched = [
        rule
        for rule in rule_set.rules
        if rule.enabled and any(_trigger_matches(trigger, event) for trigger in rule.triggers)
    ]

    if matched:
        logger.debug("matched rules: %s", [rule.name for rule in matched])
    else:
        logger.debug("no rules matched")

    return matched


def execute_rule(
    rule: Rule, event: TriggerEvent, *, conn: sqlite3.Connection, dry_run: bool = False
) -> list[ActionResult]:
    """Execute all actions for a matched rule and record each outcome to the audit log.

    All actions must be idempotent; a no-op result (e.g. user already has
    the group) is still recorded in the audit log per spec §4.4. An
    executor raising an unexpected exception is treated as a failure
    rather than propagating, so one broken action can't stop evaluation
    of other matched rules for the same event. `dry_run` is passed through
    to each executor unchanged — the engine itself has no notion of what
    "dry run" means for a given action type, only the executor does (see
    add-dry-run-mode design.md).
    """
    results = []
    for action in rule.actions:
        logger.debug("executing action: rule=%r type=%s", rule.name, action.type)

        executor = ACTION_EXECUTORS.get(action.type)
        if executor is None:
            result = ActionResult(
                status="failure", detail=f"Unknown action type: {action.type!r}"
            )
        else:
            try:
                result = executor(action, event, dry_run)
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
                result = ActionResult(status="failure", detail=f"Unexpected error: {exc}")

        logger.debug(
            "action result: rule=%r type=%s status=%s detail=%s",
            rule.name,
            action.type,
            result.status,
            result.detail,
        )

        record_event(
            conn,
            openmrs_id=event.openmrs_id,
            trigger=event.type,
            trigger_src=event.source,
            rule_name=rule.name,
            action=action.type,
            action_detail=result.action_detail,
            status=result.status,
            detail=result.detail,
        )
        results.append(result)
    return results


# Populate TRIGGER_MATCHERS / ACTION_EXECUTORS by importing the concrete
# trigger/action modules. Deferred to the end of this module (rather than
# a top-level import) because src.triggers / src.actions register back
# into this module's register_trigger()/register_action() — see their
# __init__.py docstrings.
from src.actions import register_all as _register_actions  # noqa: E402
from src.triggers import register_all as _register_triggers  # noqa: E402

_register_triggers()
_register_actions()
