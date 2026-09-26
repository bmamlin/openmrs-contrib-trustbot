from unittest.mock import patch

import pytest
import requests
from pydiscourse.exceptions import DiscourseClientError

from src.integrations.discourse import DiscourseClient


@pytest.fixture
def client():
    return DiscourseClient(
        base_url="https://talk.openmrs.org",
        api_key="secret",
        api_username="trustbot",
    )


def test_get_trust_level_returns_int(client):
    with patch.object(client._client, "user", return_value={"trust_level": 2}):
        assert client.get_trust_level("jdoe") == 2


def test_get_trust_level_propagates_client_error_unchanged(client):
    with patch.object(client._client, "user", side_effect=DiscourseClientError("not found")):
        with pytest.raises(DiscourseClientError):
            client.get_trust_level("nobody")


def test_get_trust_level_propagates_connection_error_unchanged(client):
    with patch.object(
        client._client, "user", side_effect=requests.exceptions.ConnectionError("down")
    ):
        with pytest.raises(requests.exceptions.ConnectionError):
            client.get_trust_level("jdoe")
