# discourse-workflow-trigger Specification

## Purpose

Lets `rules.yaml` react to any Discourse Workflow's HTTP action by name
— `type: workflow, name: <workflow-name>` — so which Workflow maps to
which action is declarative rule data, not a single hardcoded value
baked into service config and enforced in code.

## Requirements

### Requirement: Workflow signature is verified before any other processing
The system SHALL verify a Workflow request's HMAC-SHA256 signature (the
`X-Discourse-Workflow-Secret` header, in `sha256=<hex-digest>` form,
computed over the raw request body using the configured
`DISCOURSE_WORKFLOW_SECRET`) before taking any other action, including
before reading the workflow name or parsing the payload. An invalid or
missing signature SHALL be logged at WARNING level or above.

#### Scenario: Invalid or missing signature
- **WHEN** an incoming Workflow request's signature does not validate
  against `DISCOURSE_WORKFLOW_SECRET`
- **THEN** the service rejects the request with an HTTP 403 response,
  logs the rejection at WARNING level, and takes no further action

### Requirement: Any workflow name is accepted and routed by name
The system SHALL accept a validly-signed request bearing any
`X-Discourse-Workflow` header value — there is no single hardcoded
accepted name. The header's value becomes the event's `name`, used to
match `type: workflow` triggers in `rules.yaml`.

#### Scenario: Request from a workflow referenced by a rule
- **WHEN** a validly-signed request's `X-Discourse-Workflow` header
  value matches the `name` of a `type: workflow` trigger in an enabled
  rule
- **THEN** the system evaluates that rule against the request's payload

#### Scenario: Request from a workflow no rule references
- **WHEN** a validly-signed request's `X-Discourse-Workflow` header
  value does not match any configured rule's `type: workflow` trigger
- **THEN** the service responds HTTP 200 (per "The service acknowledges
  the request's outcome") and takes no action — the same behavior as
  any other event no rule matches

### Requirement: The payload's top-level `username` identifies the target
The system SHALL use the payload's top-level `username` field as the
target OpenMRS ID. A payload missing this field SHALL be rejected.

#### Scenario: Payload includes username
- **WHEN** a validly-signed, routed request's JSON payload includes a
  top-level `username` field
- **THEN** the system evaluates matching `type: workflow` rules using
  that value as the target OpenMRS ID, with the rest of the payload
  available to the triggered action

#### Scenario: Payload is missing username
- **WHEN** a validly-signed, routed request's JSON payload has no
  top-level `username` field, or the body is not valid JSON
- **THEN** the service rejects the request with an HTTP 400 response
  and takes no further action

### Requirement: The service acknowledges the request's outcome
The system SHALL respond with HTTP 200 when a request is accepted and
processed (regardless of whether any rule matched); HTTP 403 when
signature verification fails; and HTTP 400 for a malformed or
unparseable payload.

#### Scenario: Accepted request
- **WHEN** a request passes signature verification and payload parsing
- **THEN** the service responds with HTTP 200, whether or not any rule
  matched

#### Scenario: Rejected request
- **WHEN** a request fails signature verification or payload parsing
- **THEN** the service responds with HTTP 403 or HTTP 400 respectively
