"""Keycloak Admin REST API client (built on python-keycloak).

Wraps the Keycloak Admin REST API using the dedicated, least-privilege
service account credentials (KEYCLOAK_CLIENT_ID / KEYCLOAK_CLIENT_SECRET)
against the `OpenMRS` realm at keycloak.base_url (config.yaml). Responsible
for: looking up a user by OpenMRS ID/username, reading current group
membership, and adding/removing group membership. On connection failure,
callers in src/actions/keycloak.py expect this client to retry once after
a short delay (keycloak.retry.* in config.yaml) before raising.
"""

from __future__ import annotations


class KeycloakClient:
    """Thin wrapper around python-keycloak's KeycloakAdmin for this service's needs."""

    def __init__(self, base_url: str, realm: str, client_id: str, client_secret: str) -> None:
        raise NotImplementedError

    def get_user_groups(self, openmrs_id: str) -> list[str]:
        """Return the user's current group names, queried live (never cached)."""
        raise NotImplementedError

    def add_user_to_groups(self, openmrs_id: str, groups: list[str]) -> None:
        raise NotImplementedError

    def remove_user_from_groups(self, openmrs_id: str, groups: list[str]) -> None:
        raise NotImplementedError
