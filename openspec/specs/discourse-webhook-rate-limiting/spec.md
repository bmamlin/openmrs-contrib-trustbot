# discourse-webhook-rate-limiting Specification

## Purpose

Protects `POST /webhook/discourse` from a misconfigured or compromised
Discourse instance flooding the service with requests, by rejecting
excess requests per source IP and logging each violation.

## Requirements

### Requirement: Requests are rate limited per source IP
The system SHALL track incoming `POST /webhook/discourse` requests per
source IP address and enforce the configured limit
(`rate_limiting.discourse_webhook.max_requests` per
`rate_limiting.discourse_webhook.window_seconds`).

#### Scenario: Requests within the limit
- **WHEN** a source IP has made fewer requests than the configured
  maximum within the current window
- **THEN** the request proceeds to signature verification and the rest
  of the existing processing pipeline

### Requirement: Exceeding the limit is rejected before further processing
A request from a source IP that has exceeded the configured limit SHALL
be rejected with an HTTP 429 response before signature verification or
any other processing.

#### Scenario: Source IP exceeds the configured limit
- **WHEN** a source IP has already made `max_requests` requests within
  the current `window_seconds` window
- **THEN** the service responds with HTTP 429 and takes no further
  action — the request body is not parsed and the signature is not
  checked

### Requirement: Violations are logged
Every rejected-for-rate-limit request SHALL be logged at WARNING level or
above, identifying the source IP.

#### Scenario: A request is rejected for exceeding the rate limit
- **WHEN** the service responds with HTTP 429 for exceeding the rate
  limit
- **THEN** a WARNING-level (or higher) log entry is emitted identifying
  the source IP that was rate limited
