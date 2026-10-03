import pytest
from pydantic import ValidationError

from src.engine.models import ActionResult, Rule, RuleSet, TriggerEvent


def test_rule_set_parses_nested_triggers_and_actions():
    rule_set = RuleSet.model_validate(
        {
            "rules": [
                {
                    "name": "Grant on TL2",
                    "enabled": True,
                    "triggers": [{"type": "workflow", "name": "trusted"}],
                    "actions": [
                        {"type": "keycloak_add_groups", "groups": ["jira-users"]}
                    ],
                }
            ]
        }
    )

    rule = rule_set.rules[0]
    assert isinstance(rule, Rule)
    assert rule.triggers[0].type == "workflow"
    assert rule.triggers[0].name == "trusted"
    assert rule.actions[0].groups == ["jira-users"]


def test_trigger_event_defaults():
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe")

    assert event.name is None
    assert event.source is None
    assert event.payload == {}


def test_trigger_event_accepts_name():
    event = TriggerEvent(type="workflow", name="trusted", openmrs_id="jdoe")

    assert event.name == "trusted"


def test_action_result_accepts_known_status_values():
    for status in ("success", "no_change", "failure"):
        result = ActionResult(status=status)
        assert result.status == status


def test_action_result_rejects_unknown_status_value():
    with pytest.raises(ValidationError):
        ActionResult(status="pending")
