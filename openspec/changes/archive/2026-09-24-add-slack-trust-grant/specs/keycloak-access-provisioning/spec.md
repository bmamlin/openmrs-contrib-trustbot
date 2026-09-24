## Purpose

Grants OpenMRS community members access to downstream systems (JIRA,
Confluence) by idempotently adding their Keycloak account to one or more
groups, always against Keycloak's live state.

## ADDED Requirements

### Requirement: Group membership is queried live, never cached
The `keycloak_add_groups` action SHALL query Keycloak directly for a target
OpenMRS ID's current group memberships at execution time. The system SHALL
NOT cache or persist Keycloak group membership locally.

#### Scenario: Action executes
- **WHEN** the `keycloak_add_groups` action runs for a target OpenMRS ID
- **THEN** it queries the Keycloak Admin REST API for that user's current
  group memberships rather than reading any locally stored membership state

### Requirement: Adding groups is idempotent
The `keycloak_add_groups` action SHALL be safe to execute repeatedly with
the same input, producing no Keycloak-side change if the user already holds
the target groups.

#### Scenario: User already has all target groups
- **WHEN** the target OpenMRS ID is already a member of every group listed
  in the action
- **THEN** no group membership change is made in Keycloak and the action's
  result is reported as a no-op

#### Scenario: User has some but not all target groups
- **WHEN** the target OpenMRS ID is a member of only some of the listed
  groups
- **THEN** the action adds only the groups the user does not already have,
  and leaves existing memberships unchanged

### Requirement: Unknown OpenMRS ID is a descriptive failure
If the target OpenMRS ID does not exist in Keycloak, the action SHALL
report a failure identifying the missing user rather than creating one or
silently doing nothing.

#### Scenario: Target user does not exist
- **WHEN** the target OpenMRS ID does not exist in the configured Keycloak
  realm
- **THEN** the action reports a failure whose detail identifies that the
  user was not found

### Requirement: Transient Keycloak failures are retried once before failing
If a call to the Keycloak Admin REST API fails due to connectivity, the
system SHALL retry the call once after the configured retry delay before
reporting a failure.

#### Scenario: Keycloak temporarily unreachable
- **WHEN** a Keycloak Admin REST API call fails due to a connectivity error
- **THEN** the system waits the configured retry delay and retries the call
  exactly once

#### Scenario: Keycloak still unreachable after retry
- **WHEN** the retried call also fails
- **THEN** the action reports a failure with a message suitable for
  surfacing to the caller (e.g. "Unable to reach Keycloak. Please try again
  later.")

### Requirement: Keycloak credentials come only from environment variables
The Keycloak Admin REST API client SHALL authenticate using a client ID and
secret sourced from environment variables, and SHALL NOT read credentials
from `config.yaml`, `rules.yaml`, or any other file committed to source
control.

#### Scenario: Client authenticates
- **WHEN** the Keycloak client establishes a session with the Admin REST API
- **THEN** the client ID and secret it uses come from environment variables
  (`KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`), never from a YAML file
