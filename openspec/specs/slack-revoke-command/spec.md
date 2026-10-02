# slack-revoke-command Specification

## Purpose

Lets a trusted community member manually revoke another user's OpenMRS
community access via the `/revoke <openmrs-id>` Slack command, restricted
to the same designated private channel of vetted members used by `/trust`.

## Requirements

### Requirement: Slack request signature is verified before any processing
The system SHALL verify the Slack request signature (using the configured
signing secret) on every incoming `/revoke` command before taking any
other action, including before checking the source channel.

#### Scenario: Invalid or missing signature
- **WHEN** a `/revoke` command request's signature does not validate
  against the configured Slack signing secret
- **THEN** the service rejects the request and takes no further action

### Requirement: Commands are restricted to the designated trusted channel
The system SHALL only act on `/revoke` commands issued from the channel ID
configured as `slack.trusted_channel_id`. Commands from any other channel
SHALL be rejected silently (no action is taken and no response is sent)
and logged at WARNING level or above.

#### Scenario: Command issued from an unauthorized channel
- **WHEN** a `/revoke <openmrs-id>` command is issued from a channel other
  than the configured trusted channel
- **THEN** the service takes no action, sends no response, and logs the
  rejection at WARNING level

### Requirement: A valid command triggers rule evaluation
A `/revoke <openmrs-id>` command that passes signature verification and
originates from the trusted channel SHALL cause the system to evaluate all
enabled rules containing a `slack_revoke_command` trigger, using the given
OpenMRS ID as the target.

#### Scenario: Valid command from the trusted channel
- **WHEN** a `/revoke <openmrs-id>` command passes signature verification
  and is issued from the trusted channel
- **THEN** the system evaluates all `slack_revoke_command` rules against
  the given OpenMRS ID and executes the actions of any that match

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

### Requirement: Command issuer identity is captured
For every `/revoke` command that passes authorization checks, the system
SHALL capture the issuing Slack username, the target OpenMRS ID, the
timestamp, and the outcome, as part of the audit trail for that rule
evaluation.

#### Scenario: Any authorized /revoke command
- **WHEN** a `/revoke` command passes signature verification and channel
  restriction
- **THEN** the resulting audit record's trigger source identifies the
  issuing Slack username
