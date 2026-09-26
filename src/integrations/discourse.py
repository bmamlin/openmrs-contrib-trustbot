"""Discourse API client (built on pydiscourse).

Used for read access in support of `/trust-status` (current trust level
lookup) via DISCOURSE_API_KEY / DISCOURSE_API_USERNAME against
discourse.base_url (config.yaml). Webhook signature verification and
payload parsing for the `discourse_trust_level` trigger live in
src/api/webhooks.py and src/triggers/discourse.py, not here — this module
is only the outbound API client.

Unlike src/integrations/keycloak.py, calls here are NOT retried on
failure: /trust-status degrades gracefully by showing this section as
unavailable on any error (connectivity or a non-2xx response, e.g. the
user not existing on Discourse) rather than needing to protect a mutating
action from a spurious failure — see the add-slack-trust-status-command
design.md for the full rationale.
"""

from __future__ import annotations

from pydiscourse import DiscourseClient as _PydiscourseClient


class DiscourseClient:
    """Thin wrapper around pydiscourse's DiscourseClient for this service's needs."""

    def __init__(self, base_url: str, api_key: str, api_username: str) -> None:
        self._client = _PydiscourseClient(base_url, api_username=api_username, api_key=api_key)

    def get_trust_level(self, openmrs_id: str) -> int:
        """Return the user's current Discourse trust level (0-4).

        Any failure (connectivity, or the user not existing on Discourse)
        propagates unchanged — no retry, see module docstring.
        """
        return self._client.user(openmrs_id)["trust_level"]


_client: DiscourseClient | None = None


def build_client(base_url: str, api_key: str, api_username: str) -> DiscourseClient:
    """Construct a new DiscourseClient from explicit config values."""
    return DiscourseClient(base_url, api_key, api_username)


def set_client(client: DiscourseClient) -> None:
    """Install the module-level DiscourseClient singleton used by src/integrations/slack.py.

    Called once at startup (see src/main.py) with a real client, or by
    tests to inject a fake/mock.
    """
    global _client
    _client = client


def get_client() -> DiscourseClient:
    if _client is None:
        raise RuntimeError("Discourse client not initialized; call set_client() at startup")
    return _client
