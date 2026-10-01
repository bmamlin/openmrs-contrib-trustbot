# slack-trust-status-command Specification

## Purpose

Lets a trusted community member look up another user's current OpenMRS
community access — Keycloak groups, Discourse trust level, and recent
audit history — via the read-only `/trust-status <openmrs-id>` Slack
command, without changing any state.

## Requirements

### Requirement: Slack request signature is verified before any processing
The system SHALL verify the Slack request signature (using the configured
signing secret) on every incoming `/trust-status` command before taking
any other action, including before checking the source channel.

#### Scenario: Invalid or missing signature
- **WHEN** a `/trust-status` command request's signature does not validate
  against the configured Slack signing secret
- **THEN** the service rejects the request and takes no further action

### Requirement: Commands are restricted to the designated trusted channel
The system SHALL only act on `/trust-status` commands issued from the
channel ID configured as `slack.trusted_channel_id`. Commands from any
other channel SHALL be rejected silently (no action is taken and no
response is sent) and logged at WARNING level or above.

#### Scenario: Command issued from an unauthorized channel
- **WHEN** a `/trust-status <openmrs-id>` command is issued from a channel
  other than the configured trusted channel
- **THEN** the service takes no action, sends no response, and logs the
  rejection at WARNING level

### Requirement: The command never triggers rule evaluation
A `/trust-status` command SHALL NOT be evaluated against `rules.yaml` and
SHALL NOT cause any action (Keycloak group changes or otherwise) to be
executed. It only reads and reports existing state.

#### Scenario: Valid command from the trusted channel
- **WHEN** a `/trust-status <openmrs-id>` command passes signature
  verification and is issued from the trusted channel
- **THEN** the system looks up and reports the target's current status
  without evaluating any rule or executing any action

### Requirement: The response reports current access and recent history
For a target OpenMRS ID that exists in Keycloak, the system SHALL respond
in Slack with: the OpenMRS ID, its current Keycloak group memberships
(the community-access-relevant groups), its current Discourse trust
level, and a summary of its most recent audit log entries (action,
trigger, timestamp, and outcome).

#### Scenario: Status requested for an existing user
- **WHEN** a `/trust-status <openmrs-id>` command passes authorization
  checks and the target OpenMRS ID exists in Keycloak
- **THEN** the response includes the OpenMRS ID, its current Keycloak
  group memberships, its current Discourse trust level, and a summary of
  its most recent audit log entries

### Requirement: Partial data is shown when one data source is unavailable
If one of the three data sources (Keycloak, Discourse, or the audit log)
cannot be read when the command runs, the system SHALL still respond with
whatever data was successfully retrieved from the other sources, noting
which section is unavailable, rather than failing the entire command.

#### Scenario: Discourse is unreachable
- **WHEN** a `/trust-status` command passes authorization checks, the
  target exists in Keycloak, but the Discourse trust-level lookup fails
- **THEN** the response includes the Keycloak group memberships and
  audit history, with the Discourse trust level section noting it could
  not be retrieved

#### Scenario: Keycloak is unreachable
- **WHEN** a `/trust-status` command passes authorization checks but the
  Keycloak group-membership lookup fails
- **THEN** the response includes the Discourse trust level and audit
  history (if retrievable), with the Keycloak group membership section
  noting it could not be retrieved

### Requirement: Unknown OpenMRS ID is reported clearly
If the target OpenMRS ID does not exist in Keycloak, the system SHALL
respond with a message identifying that the user was not found, rather
than an empty or misleading status.

#### Scenario: Target OpenMRS ID does not exist
- **WHEN** a `/trust-status <openmrs-id>` command passes authorization
  checks and the target OpenMRS ID does not exist in Keycloak
- **THEN** the response states that the OpenMRS ID was not found
