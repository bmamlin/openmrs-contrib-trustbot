"""Discourse API client (built on pydiscourse).

Used for read access in support of `/trust-status` (current trust level
lookup) via DISCOURSE_API_KEY / DISCOURSE_API_USERNAME against
discourse.base_url (config.yaml). Webhook signature verification and
payload parsing for the `discourse_trust_level` trigger live in
src/api/webhooks.py and src/triggers/discourse.py, not here — this module
is only the outbound API client.
"""

from __future__ import annotations


class DiscourseClient:
    """Thin wrapper around pydiscourse's DiscourseClient for this service's needs."""

    def __init__(self, base_url: str, api_key: str, api_username: str) -> None:
        raise NotImplementedError

    def get_trust_level(self, openmrs_id: str) -> int:
        """Return the user's current Discourse trust level (0-4)."""
        raise NotImplementedError
