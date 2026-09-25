"""Trigger matchers, one module per trigger type (discourse_trust_level, slack_trust_command, ...).

`register_all()` populates the engine's TRIGGER_MATCHERS registry (see
src/engine/evaluator.py) by type string. Only trigger types with an actual
implementation are registered; a trigger type present in rules.yaml but
not registered here simply never matches (see evaluator._trigger_matches),
rather than erroring — this lets rules.yaml reference not-yet-implemented
trigger types (e.g. discourse_trust_level) without breaking evaluation.
"""

from __future__ import annotations


def register_all() -> None:
    from src.engine.evaluator import register_trigger
    from src.triggers import slack

    register_trigger("slack_trust_command", slack.matches_trust)
    register_trigger("slack_revoke_command", slack.matches_revoke)
