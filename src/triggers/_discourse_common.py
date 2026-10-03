"""Shared matching logic for the `webhook` and `workflow` trigger types.

Both types match purely by `type` + `name` equality — no payload-content
matching (deferred to a future `condition`-style enhancement, see
restructure-discourse-triggers design.md). `src/triggers/discourse_webhook.py`
and `src/triggers/discourse_workflow.py` both register this same function,
just keyed under their own type string.
"""

from __future__ import annotations

from src.engine.models import Trigger, TriggerEvent


def matches_by_name(trigger: Trigger, event: TriggerEvent) -> bool:
    """Return True if trigger and event agree on both `type` and `name`.

    `name` is a dynamic (`extra="allow"`) field on Trigger, not a
    declared model field, so a rule author forgetting to set it would
    raise AttributeError on direct attribute access rather than simply
    failing to match — getattr() with a None default avoids that.
    """
    return trigger.type == event.type and getattr(trigger, "name", None) == event.name
