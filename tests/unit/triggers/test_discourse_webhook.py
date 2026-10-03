"""Unit tests for the `webhook` trigger's matcher and dispatch.

Payload shapes below are trimmed down from real captures against the
Discourse instance (restructure-discourse-triggers tasks.md task 1.1).
"""

import pytest

from src.engine.models import Trigger, TriggerEvent
from src.triggers.discourse_webhook import build_event, matches

DISCOURSE_BASE_URL = "https://talk.openmrs.org"


def make_trigger(name="user_promoted"):
    return Trigger(type="webhook", name=name)


def test_matches_when_name_matches():
    event = TriggerEvent(type="webhook", name="user_promoted", openmrs_id="jdoe")

    assert matches(make_trigger(name="user_promoted"), event) is True


def test_does_not_match_when_name_differs():
    event = TriggerEvent(type="webhook", name="user_badge_granted", openmrs_id="jdoe")

    assert matches(make_trigger(name="user_promoted"), event) is False


def test_does_not_match_when_type_differs():
    event = TriggerEvent(type="workflow", name="user_promoted", openmrs_id="jdoe")

    assert matches(make_trigger(name="user_promoted"), event) is False


def test_build_event_returns_none_for_unregistered_event_name():
    event = build_event("some_unsupported_event", {}, discourse_base_url=DISCOURSE_BASE_URL)

    assert event is None


# --- user_promoted ---


def user_promoted_payload(**user_overrides) -> dict:
    user = {
        "id": 3569,
        "username": "testing",
        "name": "Bigscal Technologies",
        "trust_level": 2,
        "badge_count": 1,
    }
    user.update(user_overrides)
    return {"user_promoted": user}


def test_user_promoted_build_event_shape():
    event = build_event(
        "user_promoted", user_promoted_payload(), discourse_base_url=DISCOURSE_BASE_URL
    )

    assert event.type == "webhook"
    assert event.name == "user_promoted"
    assert event.openmrs_id == "testing"
    assert event.source == DISCOURSE_BASE_URL
    assert event.payload == {"trust_level": 2}


def test_user_promoted_raises_when_username_missing():
    payload = user_promoted_payload()
    del payload["user_promoted"]["username"]

    with pytest.raises(ValueError):
        build_event("user_promoted", payload, discourse_base_url=DISCOURSE_BASE_URL)


# --- user_badge_granted / user_badge_revoked ---
# Discourse's real payload for both only has a numeric user_id, never a
# username -- these tests use the forward-compatible shape (a top-level
# `username`) since that's what build_event() actually supports today;
# the real payload (no username at all) is covered by the
# raises-when-missing test below.


def user_badge_payload(*, username: str | None = None) -> dict:
    payload = {
        "user_badge": {
            "id": 864377,
            "granted_at": "2026-09-26T04:57:51.531Z",
            "created_at": "2026-09-26T04:57:51.531Z",
            "badge_id": 2,
            "user_id": 3569,
            "granted_by_id": -1,
        }
    }
    if username is not None:
        payload["username"] = username
    return payload


def test_user_badge_granted_build_event_shape_with_forward_compatible_username():
    event = build_event(
        "user_badge_granted",
        user_badge_payload(username="testing"),
        discourse_base_url=DISCOURSE_BASE_URL,
    )

    assert event.type == "webhook"
    assert event.name == "user_badge_granted"
    assert event.openmrs_id == "testing"
    assert event.payload == {"badge_id": 2}


def test_user_badge_revoked_build_event_shape_with_forward_compatible_username():
    event = build_event(
        "user_badge_revoked",
        user_badge_payload(username="testing"),
        discourse_base_url=DISCOURSE_BASE_URL,
    )

    assert event.type == "webhook"
    assert event.name == "user_badge_revoked"
    assert event.openmrs_id == "testing"


def test_user_badge_granted_raises_on_real_payload_with_no_username():
    # This is the actual shape Discourse sends today (no username at
    # all, per live capture) -- must fail loudly and log why, not
    # silently no-op, per restructure-discourse-triggers design.md.
    with pytest.raises(ValueError, match="username"):
        build_event(
            "user_badge_granted", user_badge_payload(), discourse_base_url=DISCOURSE_BASE_URL
        )


def test_user_badge_revoked_raises_on_real_payload_with_no_username():
    with pytest.raises(ValueError, match="username"):
        build_event(
            "user_badge_revoked", user_badge_payload(), discourse_base_url=DISCOURSE_BASE_URL
        )
