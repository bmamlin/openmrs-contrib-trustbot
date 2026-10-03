# discourse-webhook-trigger Specification

## Purpose

Lets `rules.yaml` react to native Discourse webhook events by name —
`type: webhook, name: <event-type>` — so a specific Discourse event
(e.g. a user being promoted a trust level) maps to a rule declaratively,
without requiring a Discourse Workflow as an intermediary.

## Requirements

### Requirement: Webhook signature is verified before any other processing
The system SHALL verify a native webhook request's HMAC-SHA256 signature
(the `X-Discourse-Event-Signature` header, in `sha256=<hex-digest>` form,
computed over the raw request body using the configured
`DISCOURSE_WEBHOOK_SECRET`) before taking any other action, including
before reading the event type or parsing the payload. An invalid or
missing signature SHALL be logged at WARNING level or above.

#### Scenario: Invalid or missing signature
- **WHEN** an incoming native webhook request's signature does not
  validate against `DISCOURSE_WEBHOOK_SECRET`
- **THEN** the service rejects the request with an HTTP 403 response,
  logs the rejection at WARNING level, and takes no further action

### Requirement: Supported event types are routed by name
The system SHALL support the `user_promoted`, `user_badge_granted`, and
`user_badge_revoked` native Discourse webhook event types, identified by
the `X-Discourse-Event` header — NOT `X-Discourse-Event-Type`, which is
only the coarser delivery category Discourse groups events under (e.g.
`user_badge_granted` and `user_badge_revoked` share the same
`X-Discourse-Event-Type: user_badge`; only `X-Discourse-Event`
distinguishes them). That header's value becomes the event's `name`,
used to match `type: webhook` triggers in `rules.yaml`. An event name
this service does not know how to parse SHALL be acknowledged (not
treated as an error) and otherwise ignored.

#### Scenario: Request for a supported event name referenced by a rule
- **WHEN** a validly-signed request's `X-Discourse-Event` header is one
  of the supported event names and matches the `name` of a
  `type: webhook` trigger in an enabled rule
- **THEN** the system parses the payload for that event name and
  evaluates that rule against it

#### Scenario: Request for a supported event name no rule references
- **WHEN** a validly-signed request's `X-Discourse-Event` header is a
  supported event name, but no configured rule's `type: webhook`
  trigger references that name
- **THEN** the service responds HTTP 200 and takes no action

#### Scenario: Request for an unsupported event name
- **WHEN** a validly-signed request's `X-Discourse-Event` header is not
  one of the event names this service knows how to parse
- **THEN** the service responds HTTP 200 and takes no action, without
  treating the unrecognized name as an error

### Requirement: user_promoted resolves the target from the serialized user
For a `user_promoted` event, the system SHALL use the payload's
serialized user's `username` field as the target OpenMRS ID, and SHALL
make the user's current `trust_level` available to the triggered
action's payload.

#### Scenario: Valid user_promoted payload
- **WHEN** a validly-signed `user_promoted` request is routed to a
  matching rule
- **THEN** the system evaluates that rule using the payload's resolved
  username as the target OpenMRS ID

### Requirement: Badge events require a username in the payload
Discourse's `user_badge_granted`/`user_badge_revoked` webhook payloads
do not currently include a username — only a numeric user ID — so the
system SHALL look for a top-level `username` field (the
forward-compatible shape, pending a currently-open Discourse Meta
request to add one) and SHALL reject the request with HTTP 400 if it is
absent, rather than silently taking no action. When present, the system
SHALL use it as the target OpenMRS ID and SHALL make the granted/revoked
badge's ID available to the triggered action's payload.

#### Scenario: Payload includes a username
- **WHEN** a validly-signed `user_badge_granted` or `user_badge_revoked`
  request is routed to a matching rule and its payload includes a
  top-level `username` field
- **THEN** the system evaluates that rule using that value as the
  target OpenMRS ID

#### Scenario: Payload has no username (Discourse's current behavior)
- **WHEN** a validly-signed `user_badge_granted` or `user_badge_revoked`
  request is routed to a matching rule and its payload has no top-level
  `username` field
- **THEN** the service rejects the request with an HTTP 400 response,
  identifying that no target OpenMRS ID could be resolved, rather than
  silently taking no action

### Requirement: The service acknowledges the request's outcome
The system SHALL respond with HTTP 200 when a request is accepted and
processed (regardless of whether any rule matched, or whether the event
name is supported); HTTP 403 when signature verification fails; and
HTTP 400 for a malformed payload, or a supported event name's payload
that cannot be resolved to a target OpenMRS ID.

#### Scenario: Accepted request
- **WHEN** a request passes signature verification and its payload (if
  for a supported event name) resolves to a target OpenMRS ID
- **THEN** the service responds with HTTP 200

#### Scenario: Rejected request
- **WHEN** a request fails signature verification, or a supported event
  name's payload cannot be resolved to a target OpenMRS ID
- **THEN** the service responds with HTTP 403 or HTTP 400 respectively
