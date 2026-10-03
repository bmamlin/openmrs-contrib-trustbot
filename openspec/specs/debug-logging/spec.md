# debug-logging Specification

## Purpose

Makes the service's existing DEBUG log level (`overview.md` §5.5,
`POST /admin/log-level`) actually useful: when enabled, every incoming
request, every rule-evaluation decision, and every action attempt
becomes visible, without ever logging a credential or a raw payload
that could contain sensitive data.

## Requirements

### Requirement: Credentials are never logged, even at DEBUG
The system SHALL exclude the `Authorization` header's value and Slack's
`token` body field from every DEBUG log entry, regardless of what else
that entry logs. This SHALL hold even when DEBUG logging of headers or
request bodies is otherwise enabled.

#### Scenario: Admin request logged at DEBUG
- **WHEN** a `POST /admin/log-level` request is logged at DEBUG level
- **THEN** the log entry does not contain the request's `Authorization`
  header value

#### Scenario: Slack command logged at DEBUG
- **WHEN** a Slack command's body is logged at DEBUG level
- **THEN** the log entry does not contain the body's `token` field value

### Requirement: Every incoming POST request is traced at DEBUG
The system SHALL log, at DEBUG level, the request headers (with
`Authorization` excluded per the above) and a curated view of the body
for every incoming request to `/webhook/discourse`, `/slack/commands`,
and `/admin/log-level`, before any authorization or validation decision
is made — so a rejected request is exactly as visible as an accepted
one.

#### Scenario: Request with an invalid signature
- **WHEN** DEBUG logging is enabled and a request to
  `/webhook/discourse` fails signature verification
- **THEN** the request's headers were already logged at DEBUG before
  the signature check ran

#### Scenario: Request that is accepted
- **WHEN** DEBUG logging is enabled and a request to any of the three
  endpoints passes its authorization checks
- **THEN** the request's headers were logged at DEBUG before those
  checks ran

### Requirement: Discourse webhook bodies are not dumped raw
For `/webhook/discourse` specifically, the system SHALL NOT log a
native webhook event's raw JSON body verbatim at DEBUG, since Discourse
controls that shape and it can embed substantial user profile data
(e.g. `user_promoted`'s full serialized user). The system SHALL instead
log only the already-parsed, curated `TriggerEvent` (type, name, target
OpenMRS ID, and the specific fields each event's parser chooses to
extract) once parsing succeeds.

#### Scenario: A user_promoted webhook is parsed
- **WHEN** DEBUG logging is enabled and a `user_promoted` webhook
  request is successfully parsed
- **THEN** the DEBUG log contains the resulting event's type, name,
  target OpenMRS ID, and trust level, but not the full raw serialized
  Discourse user object from the request body

### Requirement: Rule evaluation is traced at DEBUG
The system SHALL log, at DEBUG level, every trigger event handed to the
rules engine (its type, name, and target OpenMRS ID) and the names of
every rule that matched it — generically, for every trigger type,
without requiring a trigger-specific log statement.

#### Scenario: An event matches one or more rules
- **WHEN** DEBUG logging is enabled and a trigger event is evaluated
  against `rules.yaml`
- **THEN** the DEBUG log identifies the event and lists the name of
  every rule that matched

#### Scenario: An event matches no rules
- **WHEN** DEBUG logging is enabled and a trigger event matches no
  enabled rule
- **THEN** the DEBUG log identifies the event and indicates that no
  rule matched

### Requirement: Every action attempt and outcome is traced at DEBUG
The system SHALL log, at DEBUG level, every action a matched rule
attempts — the action type, the rule name, and the resulting outcome
(status and detail) — generically, for every action type, without
requiring an action-specific log statement.

#### Scenario: An action succeeds
- **WHEN** DEBUG logging is enabled and a matched rule's action is
  executed
- **THEN** the DEBUG log identifies the rule, the action type, and the
  resulting status and detail

#### Scenario: An action fails
- **WHEN** DEBUG logging is enabled and a matched rule's action raises
  an unexpected error or otherwise fails
- **THEN** the DEBUG log identifies the rule, the action type, and the
  failure detail

### Requirement: Keycloak connectivity retries are traced at DEBUG
The system SHALL log, at DEBUG level, each retry attempt made after a
Keycloak Admin REST API connectivity failure.

#### Scenario: A Keycloak call is retried
- **WHEN** DEBUG logging is enabled and a Keycloak Admin REST API call
  fails due to connectivity and is retried
- **THEN** the DEBUG log records that a retry occurred
