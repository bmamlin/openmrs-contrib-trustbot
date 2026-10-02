# Spec Delta

## ADDED Requirements

### Requirement: Dry-run mode makes no Keycloak-side change
While dry-run mode is active, the `keycloak_add_groups` action SHALL
still query Keycloak for the target OpenMRS ID's current group
memberships and compute which groups it would add, but SHALL NOT call
Keycloak to actually add the user to any group.

#### Scenario: Would add groups the user doesn't have
- **WHEN** dry-run mode is active and the target OpenMRS ID is missing
  one or more groups listed in the action
- **THEN** the action reports which groups it would have added, and no
  group membership change is made in Keycloak

#### Scenario: User already has all target groups
- **WHEN** dry-run mode is active and the target OpenMRS ID already
  holds every group listed in the action
- **THEN** the action reports that no change would occur, exactly as it
  would outside dry-run mode, and no group membership change is made in
  Keycloak
