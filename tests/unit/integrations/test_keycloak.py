from unittest.mock import patch

import pytest
from keycloak.exceptions import KeycloakConnectionError

from src.integrations.keycloak import KeycloakClient, UserNotFoundError


@pytest.fixture
def client():
    return KeycloakClient(
        base_url="https://id-new.openmrs.org",
        realm="OpenMRS",
        client_id="trustbot",
        client_secret="secret",
        max_retries=1,
        retry_delay_seconds=0,
    )


def test_get_user_groups_returns_group_names(client):
    with (
        patch.object(client._admin, "get_user_id", return_value="uid-1"),
        patch.object(
            client._admin,
            "get_user_groups",
            return_value=[{"name": "jira-users"}, {"name": "confluence-users"}],
        ),
    ):
        groups = client.get_user_groups("jdoe")

    assert groups == ["jira-users", "confluence-users"]


def test_get_user_groups_raises_when_user_not_found(client):
    with patch.object(client._admin, "get_user_id", return_value=None):
        with pytest.raises(UserNotFoundError):
            client.get_user_groups("nobody")


def test_add_user_to_groups_only_adds_missing_groups(client):
    with (
        patch.object(client._admin, "get_user_id", return_value="uid-1"),
        patch.object(
            client._admin, "get_user_groups", return_value=[{"name": "jira-users"}]
        ),
        patch.object(
            client._admin,
            "get_group_by_path",
            return_value={"id": "gid-confluence"},
        ) as get_group_by_path,
        patch.object(client._admin, "group_user_add") as group_user_add,
    ):
        added = client.add_user_to_groups(
            "jdoe", ["jira-users", "jira-trunk-developer", "confluence-users"]
        )

    assert set(added) == {"jira-trunk-developer", "confluence-users"}
    assert group_user_add.call_count == 2
    get_group_by_path.assert_any_call("/jira-trunk-developer")
    get_group_by_path.assert_any_call("/confluence-users")


def test_add_user_to_groups_retries_once_on_connection_error_then_succeeds(client):
    call_count = {"n": 0}

    def flaky_get_user_id(_openmrs_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise KeycloakConnectionError("connection refused")
        return "uid-1"

    with (
        patch.object(client._admin, "get_user_id", side_effect=flaky_get_user_id),
        patch.object(client._admin, "get_user_groups", return_value=[]),
        patch.object(client._admin, "get_group_by_path", return_value={"id": "gid"}),
        patch.object(client._admin, "group_user_add"),
    ):
        added = client.add_user_to_groups("jdoe", ["jira-users"])

    assert call_count["n"] == 2
    assert added == ["jira-users"]


def test_raises_after_retry_exhausted_on_persistent_connection_error(client):
    with patch.object(
        client._admin, "get_user_id", side_effect=KeycloakConnectionError("down")
    ) as get_user_id:
        with pytest.raises(KeycloakConnectionError):
            client.get_user_groups("jdoe")

    # one initial attempt + one retry (max_retries=1) = 2 calls
    assert get_user_id.call_count == 2
