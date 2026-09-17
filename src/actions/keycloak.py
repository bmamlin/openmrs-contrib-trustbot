"""The `keycloak_add_groups` and `keycloak_remove_groups` actions.

Add or remove an OpenMRS ID's Keycloak group memberships via
src/integrations/keycloak.py. Both actions must be idempotent: adding a
group the user already has (or removing one they don't have) is a no-op
that still returns a result recorded to the audit log with
status='no_change' (see openspec/specs/overview.md §4.4, §5.4). Group
membership is always queried live from Keycloak — never cached.
"""

from __future__ import annotations

from typing import Any

from src.engine.models import Action


def add_groups(action: Action, openmrs_id: str) -> Any:
    """Add openmrs_id to the groups listed in the action; idempotent."""
    raise NotImplementedError


def remove_groups(action: Action, openmrs_id: str) -> Any:
    """Remove openmrs_id from the groups listed in the action; idempotent."""
    raise NotImplementedError
