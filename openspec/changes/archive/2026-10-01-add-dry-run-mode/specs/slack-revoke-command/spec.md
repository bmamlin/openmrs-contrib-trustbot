# Spec Delta

## MODIFIED Requirements

### Requirement: The caller receives a clear response for every valid command
The system SHALL respond in Slack with a clear outcome message for every
`/revoke` command that passes authorization checks (signature + channel).
If dry-run mode is active, the response SHALL clearly state that no real
change was made, rather than using the normal success/no-change wording.

#### Scenario: Access revoked
- **WHEN** the triggered rule's action successfully removes the target
  user from one or more Keycloak groups
- **THEN** the service responds in Slack with a confirmation message

#### Scenario: Target already lacks the access being revoked
- **WHEN** the target OpenMRS ID already holds none of the groups the
  matching rule would remove
- **THEN** the service responds with a message indicating the user is
  already not trusted, and the event is still recorded in the audit log
  noting no change was made

#### Scenario: Target OpenMRS ID does not exist
- **WHEN** the target OpenMRS ID does not exist in Keycloak
- **THEN** the service responds with a descriptive failure message and
  logs the error

#### Scenario: Dry-run mode is active
- **WHEN** a `/revoke <openmrs-id>` command passes authorization checks
  while dry-run mode is active
- **THEN** the service responds with a message stating that the
  revocation was simulated and no real change was made, instead of the
  normal "revoked" or "already not trusted" wording
