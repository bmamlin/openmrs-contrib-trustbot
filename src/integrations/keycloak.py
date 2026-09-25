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

import time

from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakConnectionError


class UserNotFoundError(Exception):
    """The given OpenMRS ID does not exist in Keycloak."""

    def __init__(self, openmrs_id: str) -> None:
        self.openmrs_id = openmrs_id
        super().__init__(f"OpenMRS ID '{openmrs_id}' not found in Keycloak")


class KeycloakClient:
    """Thin wrapper around python-keycloak's KeycloakAdmin for this service's needs.

    Group membership is always fetched live from Keycloak (never cached).
    Connectivity failures are retried once, per `keycloak.retry.*`
    (config.yaml), before the underlying KeycloakConnectionError propagates.
    """

    def __init__(
        self,
        base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        *,
        max_retries: int = 1,
        retry_delay_seconds: int = 2,
    ) -> None:
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._admin = KeycloakAdmin(
            server_url=base_url,
            realm_name=realm,
            client_id=client_id,
            client_secret_key=client_secret,
            grant_type="client_credentials",
        )

    def _call_with_retry(self, fn, *args, **kwargs):
        attempts = self._max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return fn(*args, **kwargs)
            except KeycloakConnectionError:
                if attempt >= attempts:
                    raise
                time.sleep(self._retry_delay_seconds)

    def _require_user_id(self, openmrs_id: str) -> str:
        user_id = self._call_with_retry(self._admin.get_user_id, openmrs_id)
        if user_id is None:
            raise UserNotFoundError(openmrs_id)
        return user_id

    def _group_names_for_user_id(self, user_id: str) -> list[str]:
        groups = self._call_with_retry(self._admin.get_user_groups, user_id)
        return [group["name"] for group in groups]

    def get_user_groups(self, openmrs_id: str) -> list[str]:
        """Return the user's current group names, queried live (never cached)."""
        user_id = self._require_user_id(openmrs_id)
        return self._group_names_for_user_id(user_id)

    def add_user_to_groups(self, openmrs_id: str, groups: list[str]) -> list[str]:
        """Add openmrs_id to each of `groups` it isn't already in.

        Idempotent: existing memberships are left untouched. Returns the
        list of group names actually added (empty if the user already had
        all of them). Raises UserNotFoundError if openmrs_id doesn't exist.
        """
        user_id = self._require_user_id(openmrs_id)
        current = set(self._group_names_for_user_id(user_id))

        added: list[str] = []
        for group_name in groups:
            if group_name in current:
                continue
            group = self._call_with_retry(self._admin.get_group_by_path, f"/{group_name}")
            self._call_with_retry(self._admin.group_user_add, user_id, group["id"])
            added.append(group_name)
        return added

    def remove_user_from_groups(self, openmrs_id: str, groups: list[str]) -> list[str]:
        """Remove openmrs_id from each of `groups` it is currently in.

        Idempotent: groups the user doesn't have are left alone (not an
        error). Returns the list of group names actually removed (empty
        if the user held none of them). Raises UserNotFoundError if
        openmrs_id doesn't exist.
        """
        user_id = self._require_user_id(openmrs_id)
        current = set(self._group_names_for_user_id(user_id))

        removed: list[str] = []
        for group_name in groups:
            if group_name not in current:
                continue
            group = self._call_with_retry(self._admin.get_group_by_path, f"/{group_name}")
            self._call_with_retry(self._admin.group_user_remove, user_id, group["id"])
            removed.append(group_name)
        return removed


_client: KeycloakClient | None = None


def build_client(base_url: str, realm: str, client_id: str, client_secret: str, **kwargs) -> KeycloakClient:
    """Construct a new KeycloakClient from explicit config values."""
    return KeycloakClient(base_url, realm, client_id, client_secret, **kwargs)


def set_client(client: KeycloakClient) -> None:
    """Install the module-level KeycloakClient singleton used by src/actions/keycloak.py.

    Called once at startup (see src/main.py) with a real client, or by
    tests to inject a fake/mock.
    """
    global _client
    _client = client


def get_client() -> KeycloakClient:
    if _client is None:
        raise RuntimeError("Keycloak client not initialized; call set_client() at startup")
    return _client
