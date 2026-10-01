# Spec Delta

## Purpose

Automatically grants OpenMRS community members access when they reach
Discourse trust level 2, by receiving and verifying a webhook call from a
Discourse Workflow configured on the community's Discourse instance, and
feeding it into the rules engine as a `discourse_trust_level` trigger
event.

## ADDED Requirements

### Requirement: Webhook signature is verified before any other processing
The system SHALL verify the webhook request's HMAC-SHA256 signature
(the `X-Discourse-Workflow-Secret` header, in `sha256=<hex-digest>` form,
computed over the raw request body using the configured shared secret)
before taking any other action, including before checking the workflow
name or parsing the payload.

#### Scenario: Invalid or missing signature
- **WHEN** an incoming webhook request's signature does not validate
  against the configured shared secret
- **THEN** the service rejects the request with an HTTP 403 response and
  takes no further action

### Requirement: Requests are restricted to the configured workflow
The system SHALL only act on requests whose `X-Discourse-Workflow` header
matches the configured expected workflow name. Requests with any other
value SHALL be rejected.

#### Scenario: Unrecognized workflow name
- **WHEN** a validly-signed request's `X-Discourse-Workflow` header does
  not match the configured expected value
- **THEN** the service rejects the request with an HTTP 4xx response and
  takes no further action

### Requirement: Stale requests are rejected as potential replays
The system SHALL reject a request whose payload `timestamp` falls outside
the configured replay window (`discourse.webhook.replay_window_seconds`),
even if the signature is valid.

#### Scenario: Timestamp outside the replay window
- **WHEN** a validly-signed, correctly-routed request's payload
  `timestamp` is older than the configured replay window
- **THEN** the service rejects the request with an HTTP 4xx response and
  takes no further action

### Requirement: A valid request triggers rule evaluation
A request that passes signature verification, workflow-name validation,
and replay-window checking SHALL cause the system to evaluate all enabled
rules containing a `discourse_trust_level` trigger, using the payload's
`username` as the target OpenMRS ID.

#### Scenario: Valid trust-level-crossing request
- **WHEN** a request passes all authorization and freshness checks
- **THEN** the system evaluates all `discourse_trust_level` rules against
  the payload's `username` and executes the actions of any that match

### Requirement: Trigger matches at or above the configured threshold
A `discourse_trust_level` trigger with a configured `threshold` SHALL
match when the request's `new_trust_level` is greater than or equal to
that threshold, regardless of whether this is the user's first time
crossing it.

#### Scenario: New trust level meets the threshold
- **WHEN** a rule's `discourse_trust_level` trigger has `threshold: 2` and
  an incoming request reports `new_trust_level: 2` (or higher)
- **THEN** the trigger matches

#### Scenario: New trust level is below the threshold
- **WHEN** a rule's `discourse_trust_level` trigger has `threshold: 2` and
  an incoming request reports `new_trust_level: 1`
- **THEN** the trigger does not match

### Requirement: The service acknowledges the request's outcome
The system SHALL respond with HTTP 200 when a request is accepted and
processed (regardless of whether any rule matched); HTTP 403 when
signature verification fails; and an HTTP 4xx status for any other
rejected request (unrecognized workflow name, stale timestamp, or
malformed payload).

#### Scenario: Accepted request
- **WHEN** a request passes all checks and is handed to the rules engine
- **THEN** the service responds with HTTP 200

#### Scenario: Rejected request
- **WHEN** a request fails signature verification, workflow-name
  validation, replay-window checking, or payload parsing
- **THEN** the service responds with an HTTP 4xx status
