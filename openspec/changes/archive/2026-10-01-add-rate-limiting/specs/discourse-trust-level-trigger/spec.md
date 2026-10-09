# Spec Delta

## MODIFIED Requirements

### Requirement: Webhook signature is verified before any other processing
The system SHALL verify the webhook request's HMAC-SHA256 signature
(the `X-Discourse-Workflow-Signature` header, in `sha256=<hex-digest>` form,
computed over the raw request body using the configured shared secret)
before taking any other action, including before checking the workflow
name or parsing the payload. An invalid or missing signature SHALL be
logged at WARNING level or above.

#### Scenario: Invalid or missing signature
- **WHEN** an incoming webhook request's signature does not validate
  against the configured shared secret
- **THEN** the service rejects the request with an HTTP 403 response,
  logs the rejection at WARNING level, and takes no further action

### Requirement: Requests are restricted to the configured workflow
The system SHALL only act on requests whose `X-Discourse-Workflow` header
matches the configured expected workflow name. Requests with any other
value SHALL be rejected and logged at WARNING level or above.

#### Scenario: Unrecognized workflow name
- **WHEN** a validly-signed request's `X-Discourse-Workflow` header does
  not match the configured expected value
- **THEN** the service rejects the request with an HTTP 4xx response,
  logs the rejection at WARNING level, and takes no further action
