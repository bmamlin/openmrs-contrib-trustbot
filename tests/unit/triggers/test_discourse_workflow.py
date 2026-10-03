import pytest

from src.engine.models import Trigger, TriggerEvent
from src.triggers.discourse_workflow import build_event, matches

DISCOURSE_BASE_URL = "https://talk.openmrs.org"


def make_trigger(name="trusted"):
    return Trigger(type="workflow", name=name)


def test_matches_when_name_matches():
    event = TriggerEvent(type="workflow", name="trusted", openmrs_id="jdoe")

    assert matches(make_trigger(name="trusted"), event) is True


def test_does_not_match_when_name_differs():
    event = TriggerEvent(type="workflow", name="untrusted", openmrs_id="jdoe")

    assert matches(make_trigger(name="trusted"), event) is False


def test_does_not_match_when_type_differs():
    event = TriggerEvent(type="webhook", name="trusted", openmrs_id="jdoe")

    assert matches(make_trigger(name="trusted"), event) is False


def test_does_not_match_and_does_not_raise_when_trigger_name_is_unset():
    # Trigger.name is a dynamic (extra="allow") field, not a declared
    # model field -- a rule author forgetting to set it must fail to
    # match, not raise AttributeError.
    trigger = Trigger(type="workflow")
    event = TriggerEvent(type="workflow", name="trusted", openmrs_id="jdoe")

    assert matches(trigger, event) is False


def test_build_event_shape():
    event = build_event(
        "trusted",
        {"username": "jdoe", "old_trust_level": 1, "new_trust_level": 2},
        discourse_base_url=DISCOURSE_BASE_URL,
    )

    assert event.type == "workflow"
    assert event.name == "trusted"
    assert event.openmrs_id == "jdoe"
    assert event.source == DISCOURSE_BASE_URL
    assert event.payload == {"old_trust_level": 1, "new_trust_level": 2}


def test_build_event_raises_when_username_missing():
    with pytest.raises(ValueError):
        build_event(
            "trusted",
            {"old_trust_level": 1, "new_trust_level": 2},
            discourse_base_url=DISCOURSE_BASE_URL,
        )
