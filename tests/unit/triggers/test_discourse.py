from src.engine.models import Trigger
from src.triggers.discourse import build_trust_level_event, matches


def make_trigger(threshold=2):
    return Trigger(type="discourse_trust_level", threshold=threshold)


def test_matches_when_new_trust_level_meets_threshold():
    event = build_trust_level_event(
        {"username": "jdoe", "old_trust_level": 1, "new_trust_level": 2, "timestamp": "x"},
        discourse_base_url="https://talk.openmrs.org",
    )

    assert matches(make_trigger(threshold=2), event) is True


def test_matches_when_new_trust_level_exceeds_threshold():
    event = build_trust_level_event(
        {"username": "jdoe", "old_trust_level": 2, "new_trust_level": 3, "timestamp": "x"},
        discourse_base_url="https://talk.openmrs.org",
    )

    assert matches(make_trigger(threshold=2), event) is True


def test_does_not_match_when_new_trust_level_is_below_threshold():
    event = build_trust_level_event(
        {"username": "jdoe", "old_trust_level": 0, "new_trust_level": 1, "timestamp": "x"},
        discourse_base_url="https://talk.openmrs.org",
    )

    assert matches(make_trigger(threshold=2), event) is False


def test_build_trust_level_event_shape():
    event = build_trust_level_event(
        {"username": "jdoe", "old_trust_level": 1, "new_trust_level": 2, "timestamp": "x"},
        discourse_base_url="https://talk.openmrs.org",
    )

    assert event.type == "discourse_trust_level"
    assert event.openmrs_id == "jdoe"
    assert event.source == "https://talk.openmrs.org"
    assert event.payload == {"old_trust_level": 1, "new_trust_level": 2}
