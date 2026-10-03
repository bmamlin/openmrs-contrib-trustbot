"""The `workflow` trigger type: Discourse Workflow HTTP action payloads.

Matches a rule's `{type: workflow, name: "<workflow-name>"}` trigger
against the `X-Discourse-Workflow` header's value — any name a rule
references is accepted, not a single hardcoded one (see
restructure-discourse-triggers proposal.md for why). The Workflow author
(the OpenMRS team, via the Workflow's own HTTP action step) fully
controls the payload shape; the only contract this module enforces is a
top-level `username` field, used as the target OpenMRS ID. Signature
verification and header/payload parsing happen in src/api/webhooks.py
before a TriggerEvent exists — this module only matches/builds events.
"""

from __future__ import annotations

from src.engine.models import TriggerEvent
from src.triggers._discourse_common import matches_by_name

matches = matches_by_name


def build_event(workflow_name: str, payload: dict, *, discourse_base_url: str) -> TriggerEvent:
    """Build a `workflow` TriggerEvent from an already-verified, already-parsed payload.

    Raises ValueError if `payload` has no top-level `username` field.

    `source` is the configured Discourse instance URL — there's no
    per-request issuer the way Slack commands have an issuing username,
    matching the audit schema's own `trigger_src` example ("Discourse
    webhook URL").
    """
    if "username" not in payload:
        raise ValueError("workflow payload missing required 'username' field")

    rest = {k: v for k, v in payload.items() if k != "username"}
    return TriggerEvent(
        type="workflow",
        name=workflow_name,
        openmrs_id=payload["username"],
        source=discourse_base_url,
        payload=rest,
    )
