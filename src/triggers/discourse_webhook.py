"""The `webhook` trigger type: native Discourse webhook events.

Matches a rule's `{type: webhook, name: "<event-type>"}` trigger against
the `X-Discourse-Event` header's value — NOT `X-Discourse-Event-Type`,
which is only the coarse delivery category Discourse groups events under
(confirmed via live capture): `user_promoted` has its own category, so
both headers carry the same value for it, but `user_badge_granted` and
`user_badge_revoked` both fall under the `user_badge` category — only
`X-Discourse-Event` actually distinguishes them.

Unlike `workflow` payloads (fully controlled by the OpenMRS team), each
native event's JSON shape is Discourse-defined, so every supported event
name needs its own small parser in PAYLOAD_PARSERS. An event name with no
registered parser is not an error: build_event() returns None and the
caller (src/api/webhooks.py) acknowledges with HTTP 200 and takes no
action, since Discourse's webhook admin UI can be configured to send
broader event categories than this service parses. A registered parser
that cannot resolve a target OpenMRS ID from the payload instead raises
ValueError — a real error (HTTP 400), not a silent no-op, so it's visible
in logs rather than quietly doing nothing.

Known gap (confirmed via live capture, not yet fixed upstream): Discourse
badge webhook payloads (`user_badge_granted`/`user_badge_revoked`) carry
only a numeric `user_id`, never a `username` — unlike `user_promoted`,
whose payload embeds the full serialized user, username included. There
is an open Discourse Meta request to add `username` to badge payloads.
Until then, the badge parsers below support a payload with a top-level
`username` (the forward-compatible shape) and raise ValueError when it's
absent, so a rule using these triggers fails loudly and explains why in
the logs, and will simply start working the moment Discourse adds the
field — no code change needed here.
"""

from __future__ import annotations

from collections.abc import Callable

from src.engine.models import TriggerEvent
from src.triggers._discourse_common import matches_by_name

matches = matches_by_name


def _parse_user_promoted(payload: dict) -> tuple[str, dict]:
    user = payload.get("user_promoted", {})
    username = user.get("username")
    if not username:
        raise ValueError("user_promoted payload missing 'user_promoted.username'")
    return username, {"trust_level": user.get("trust_level")}


def _parse_user_badge_event(payload: dict) -> tuple[str, dict]:
    user_badge = payload.get("user_badge", {})
    # Discourse's actual payload today only has a numeric user_id here --
    # no username. Accept a top-level `username` as the forward-compatible
    # shape (per Meta discussion requesting Discourse add it to this
    # payload); raise loudly when absent rather than silently no-op, so
    # this starts working automatically once Discourse adds the field.
    username = payload.get("username") or user_badge.get("username")
    if not username:
        raise ValueError(
            "user_badge payload has no 'username' -- Discourse does not yet include it for "
            "badge events (only a numeric user_id); cannot resolve the target OpenMRS ID"
        )
    return username, {"badge_id": user_badge.get("badge_id")}


# event name (X-Discourse-Event, not X-Discourse-Event-Type) -> parser
PAYLOAD_PARSERS: dict[str, Callable[[dict], tuple[str, dict]]] = {
    "user_promoted": _parse_user_promoted,
    "user_badge_granted": _parse_user_badge_event,
    "user_badge_revoked": _parse_user_badge_event,
}


def build_event(event_name: str, payload: dict, *, discourse_base_url: str) -> TriggerEvent | None:
    """Build a `webhook` TriggerEvent from an already-verified, already-parsed payload.

    Returns None if `event_name` has no registered parser (not an error
    — the caller should acknowledge and take no action). Raises
    ValueError if a registered parser cannot resolve a target OpenMRS ID
    from the payload (a real error — the caller should reject with 400).

    `source` is the configured Discourse instance URL — there's no
    per-request issuer the way Slack commands have an issuing username,
    matching the audit schema's own `trigger_src` example ("Discourse
    webhook URL").
    """
    parser = PAYLOAD_PARSERS.get(event_name)
    if parser is None:
        return None

    openmrs_id, normalized_payload = parser(payload)
    return TriggerEvent(
        type="webhook",
        name=event_name,
        openmrs_id=openmrs_id,
        source=discourse_base_url,
        payload=normalized_payload,
    )
