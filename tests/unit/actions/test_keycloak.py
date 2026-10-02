from unittest.mock import MagicMock

import pytest
from keycloak.exceptions import KeycloakConnectionError

from src.actions.keycloak import add_groups, remove_groups
from src.engine.models import Action, TriggerEvent
from src.integrations import keycloak as keycloak_integration
from src.integrations.keycloak import UserNotFoundError


@pytest.fixture(autouse=True)
def reset_client():
    yield
    keycloak_integration._client = None


def make_event(openmrs_id="jdoe"):
    return TriggerEvent(type="slack_trust_command", openmrs_id=openmrs_id, source="alice")


def make_action(groups=("jira-users", "jira-trunk-developer", "confluence-users")):
    return Action(type="keycloak_add_groups", groups=list(groups))


def make_revoke_action(groups=("jira-users", "jira-trunk-developer", "confluence-users")):
    return Action(type="keycloak_remove_groups", groups=list(groups))


def test_add_groups_success_when_groups_are_missing():
    client = MagicMock()
    client.add_user_to_groups.return_value = ["jira-users", "confluence-users"]
    keycloak_integration.set_client(client)

    result = add_groups(make_action(), make_event())

    assert result.status == "success"
    assert "jira-users" in result.action_detail


def test_add_groups_no_change_when_already_member():
    client = MagicMock()
    client.add_user_to_groups.return_value = []
    keycloak_integration.set_client(client)

    result = add_groups(make_action(), make_event())

    assert result.status == "no_change"
    assert "jdoe" in result.detail


def test_add_groups_failure_when_user_not_found():
    client = MagicMock()
    client.add_user_to_groups.side_effect = UserNotFoundError("nobody")
    keycloak_integration.set_client(client)

    result = add_groups(make_action(), make_event(openmrs_id="nobody"))

    assert result.status == "failure"
    assert "nobody" in result.detail


def test_add_groups_failure_when_keycloak_unreachable():
    client = MagicMock()
    client.add_user_to_groups.side_effect = KeycloakConnectionError("down")
    keycloak_integration.set_client(client)

    result = add_groups(make_action(), make_event())

    assert result.status == "failure"
    assert "Unable to reach Keycloak" in result.detail


def test_add_groups_dry_run_with_groups_missing():
    client = MagicMock()
    client.add_user_to_groups.return_value = ["jira-users", "confluence-users"]
    keycloak_integration.set_client(client)

    result = add_groups(make_action(), make_event(), dry_run=True)

    assert result.status == "dry_run"
    assert "jira-users" in result.action_detail
    client.add_user_to_groups.assert_called_once_with(
        "jdoe", ["jira-users", "jira-trunk-developer", "confluence-users"], dry_run=True
    )


def test_add_groups_dry_run_with_nothing_to_add():
    client = MagicMock()
    client.add_user_to_groups.return_value = []
    keycloak_integration.set_client(client)

    result = add_groups(make_action(), make_event(), dry_run=True)

    assert result.status == "dry_run"
    assert "jdoe" in result.detail


def test_add_groups_dry_run_failure_when_user_not_found_is_still_failure():
    client = MagicMock()
    client.add_user_to_groups.side_effect = UserNotFoundError("nobody")
    keycloak_integration.set_client(client)

    result = add_groups(make_action(), make_event(openmrs_id="nobody"), dry_run=True)

    assert result.status == "failure"
    assert "nobody" in result.detail


def test_remove_groups_success_when_groups_are_present():
    client = MagicMock()
    client.remove_user_from_groups.return_value = ["jira-users", "confluence-users"]
    keycloak_integration.set_client(client)

    result = remove_groups(make_revoke_action(), make_event())

    assert result.status == "success"
    assert "jira-users" in result.action_detail


def test_remove_groups_no_change_when_not_a_member():
    client = MagicMock()
    client.remove_user_from_groups.return_value = []
    keycloak_integration.set_client(client)

    result = remove_groups(make_revoke_action(), make_event())

    assert result.status == "no_change"
    assert "jdoe" in result.detail


def test_remove_groups_failure_when_user_not_found():
    client = MagicMock()
    client.remove_user_from_groups.side_effect = UserNotFoundError("nobody")
    keycloak_integration.set_client(client)

    result = remove_groups(make_revoke_action(), make_event(openmrs_id="nobody"))

    assert result.status == "failure"
    assert "nobody" in result.detail


def test_remove_groups_failure_when_keycloak_unreachable():
    client = MagicMock()
    client.remove_user_from_groups.side_effect = KeycloakConnectionError("down")
    keycloak_integration.set_client(client)

    result = remove_groups(make_revoke_action(), make_event())

    assert result.status == "failure"
    assert "Unable to reach Keycloak" in result.detail


def test_remove_groups_dry_run_with_groups_present():
    client = MagicMock()
    client.remove_user_from_groups.return_value = ["jira-users", "confluence-users"]
    keycloak_integration.set_client(client)

    result = remove_groups(make_revoke_action(), make_event(), dry_run=True)

    assert result.status == "dry_run"
    assert "jira-users" in result.action_detail
    client.remove_user_from_groups.assert_called_once_with(
        "jdoe", ["jira-users", "jira-trunk-developer", "confluence-users"], dry_run=True
    )


def test_remove_groups_dry_run_with_nothing_to_remove():
    client = MagicMock()
    client.remove_user_from_groups.return_value = []
    keycloak_integration.set_client(client)

    result = remove_groups(make_revoke_action(), make_event(), dry_run=True)

    assert result.status == "dry_run"
    assert "jdoe" in result.detail


def test_remove_groups_dry_run_failure_when_user_not_found_is_still_failure():
    client = MagicMock()
    client.remove_user_from_groups.side_effect = UserNotFoundError("nobody")
    keycloak_integration.set_client(client)

    result = remove_groups(make_revoke_action(), make_event(openmrs_id="nobody"), dry_run=True)

    assert result.status == "failure"
    assert "nobody" in result.detail
