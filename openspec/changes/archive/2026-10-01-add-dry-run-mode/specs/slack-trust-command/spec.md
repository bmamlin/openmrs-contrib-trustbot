# Spec Delta

## MODIFIED Requirements

### Requirement: The caller receives a clear response for every valid command
The system SHALL respond in Slack with a clear outcome message for every
`/trust` command that passes authorization checks (signature + channel).
If dry-run mode is active, the response SHALL clearly state that no real
change was made, rather than using the normal success/no-change wording.

#### Scenario: Access granted
- **WHEN** the triggered rule's action successfully adds the target user to
  one or more Keycloak groups
- **THEN** the service responds in Slack with a confirmation message

#### Scenario: Target already has the access being granted
- **WHEN** the target OpenMRS ID already holds every group the matching
  rule would grant
- **THEN** the service responds with a message indicating the user is
  already trusted (e.g. "`foobar` is already trusted."), and the event is
  still recorded in the audit log noting no change was made

#### Scenario: Target OpenMRS ID does not exist
- **WHEN** the target OpenMRS ID does not exist in Keycloak
- **THEN** the service responds with a descriptive failure message and logs
  the error

#### Scenario: Dry-run mode is active
- **WHEN** a `/trust <openmrs-id>` command passes authorization checks
  while dry-run mode is active
- **THEN** the service responds with a message stating that the grant
  was simulated and no real change was made, instead of the normal
  "granted" or "already trusted" wording
