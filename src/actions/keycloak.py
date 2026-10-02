"""The `keycloak_add_groups` and `keycloak_remove_groups` actions.

Add or remove an OpenMRS ID's Keycloak group memberships via
src/integrations/keycloak.py. Both actions must be idempotent: adding a
group the user already has (or removing one they don't have) is a no-op
that still returns a result recorded to the audit log with
status='no_change' (see openspec/specs/overview.md §4.4, §5.4). Group
membership is always queried live from Keycloak — never cached.
"""

from __future__ import annotations

import json

from keycloak.exceptions import KeycloakConnectionError

from src.engine.models import Action, ActionResult, TriggerEvent
from src.integrations import keycloak as keycloak_integration
from src.integrations.keycloak import UserNotFoundError


def add_groups(action: Action, event: TriggerEvent, dry_run: bool = False) -> ActionResult:
    """Add event.openmrs_id to the groups listed in the action; idempotent.

    When dry_run is True, current membership is still queried live and the
    would-be-added groups are still computed and reported, but no change
    is made in Keycloak — the result's status is "dry_run" rather than
    "success"/"no_change" (see add-dry-run-mode design.md).
    """
    client = keycloak_integration.get_client()
    groups: list[str] = action.groups

    try:
        added = client.add_user_to_groups(event.openmrs_id, groups, dry_run=dry_run)
    except UserNotFoundError as exc:
        return ActionResult(status="failure", detail=str(exc))
    except KeycloakConnectionError:
        return ActionResult(
            status="failure",
            detail="Unable to reach Keycloak. Please try again later.",
        )

    if not added:
        detail = f"'{event.openmrs_id}' is already a member of: {', '.join(groups)}"
        return ActionResult(status="dry_run" if dry_run else "no_change", detail=detail)

    if dry_run:
        return ActionResult(
            status="dry_run",
            detail=f"Would add '{event.openmrs_id}' to: {', '.join(added)}",
            action_detail=json.dumps(added),
        )

    return ActionResult(
        status="success",
        detail=f"Added '{event.openmrs_id}' to: {', '.join(added)}",
        action_detail=json.dumps(added),
    )


def remove_groups(action: Action, event: TriggerEvent, dry_run: bool = False) -> ActionResult:
    """Remove event.openmrs_id from the groups listed in the action; idempotent.

    When dry_run is True, current membership is still queried live and the
    would-be-removed groups are still computed and reported, but no change
    is made in Keycloak — the result's status is "dry_run" rather than
    "success"/"no_change" (see add-dry-run-mode design.md).
    """
    client = keycloak_integration.get_client()
    groups: list[str] = action.groups

    try:
        removed = client.remove_user_from_groups(event.openmrs_id, groups, dry_run=dry_run)
    except UserNotFoundError as exc:
        return ActionResult(status="failure", detail=str(exc))
    except KeycloakConnectionError:
        return ActionResult(
            status="failure",
            detail="Unable to reach Keycloak. Please try again later.",
        )

    if not removed:
        detail = f"'{event.openmrs_id}' is not a member of any of: {', '.join(groups)}"
        return ActionResult(status="dry_run" if dry_run else "no_change", detail=detail)

    if dry_run:
        return ActionResult(
            status="dry_run",
            detail=f"Would remove '{event.openmrs_id}' from: {', '.join(removed)}",
            action_detail=json.dumps(removed),
        )

    return ActionResult(
        status="success",
        detail=f"Removed '{event.openmrs_id}' from: {', '.join(removed)}",
        action_detail=json.dumps(removed),
    )
