# Spec Delta

## ADDED Requirements

### Requirement: Dry-run mode makes no Keycloak-side change
While dry-run mode is active, the `keycloak_remove_groups` action SHALL
still query Keycloak for the target OpenMRS ID's current group
memberships and compute which groups it would remove, but SHALL NOT call
Keycloak to actually remove the user from any group.

#### Scenario: Would remove groups the user has
- **WHEN** dry-run mode is active and the target OpenMRS ID currently
  holds one or more groups listed in the action
- **THEN** the action reports which groups it would have removed, and
  no group membership change is made in Keycloak

#### Scenario: User already lacks all target groups
- **WHEN** dry-run mode is active and the target OpenMRS ID holds none
  of the groups listed in the action
- **THEN** the action reports that no change would occur, exactly as it
  would outside dry-run mode, and no group membership change is made in
  Keycloak
