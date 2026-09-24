from src.engine.models import Trigger, TriggerEvent
from src.triggers.slack import build_trust_event, matches_trust


def test_matches_trust_when_types_align():
    trigger = Trigger(type="slack_trust_command")
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe")

    assert matches_trust(trigger, event) is True


def test_build_trust_event_from_trusted_channel():
    command = {
        "channel_id": "C0123456789",
        "text": "jdoe",
        "user_name": "alice",
    }

    event = build_trust_event(command, trusted_channel_id="C0123456789")

    assert event is not None
    assert event.type == "slack_trust_command"
    assert event.openmrs_id == "jdoe"
    assert event.source == "alice"


def test_build_trust_event_rejects_other_channel_with_no_event():
    command = {
        "channel_id": "C_UNAUTHORIZED",
        "text": "jdoe",
        "user_name": "alice",
    }

    event = build_trust_event(command, trusted_channel_id="C0123456789")

    assert event is None


def test_build_trust_event_strips_whitespace_from_target_id():
    command = {
        "channel_id": "C0123456789",
        "text": "  jdoe  ",
        "user_name": "alice",
    }

    event = build_trust_event(command, trusted_channel_id="C0123456789")

    assert event.openmrs_id == "jdoe"
