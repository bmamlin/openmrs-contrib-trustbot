# admin-log-level-api Specification

## Purpose

Lets an operator change the running service's application log level at
runtime — without a restart — through a protected admin endpoint, for
diagnosing issues on an already-running process.

## Requirements

### Requirement: Changing the log level requires authorization
When `config.yaml`'s `admin.require_auth` is `true` (the default), the
system SHALL require a valid bearer token (matching the configured
`ADMIN_API_TOKEN`) on every `POST /admin/log-level` request, checked
before any other processing. A missing or invalid token SHALL be rejected
with HTTP 401 and the log level SHALL remain unchanged.

#### Scenario: Missing bearer token
- **WHEN** a `POST /admin/log-level` request has no `Authorization` header
  and `admin.require_auth` is `true`
- **THEN** the service rejects the request with HTTP 401 and the running
  log level is unchanged

#### Scenario: Invalid bearer token
- **WHEN** a `POST /admin/log-level` request's bearer token does not
  match the configured `ADMIN_API_TOKEN` and `admin.require_auth` is
  `true`
- **THEN** the service rejects the request with HTTP 401 and the running
  log level is unchanged

#### Scenario: Authorization disabled
- **WHEN** `admin.require_auth` is `false`
- **THEN** a `POST /admin/log-level` request proceeds without a bearer
  token check

### Requirement: A valid level is applied at runtime without a restart
A request that passes authorization and names one of the recognized
levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`) SHALL change the running
service's application log level immediately, with no process restart,
and SHALL confirm the newly active level in its response.

#### Scenario: Valid level change
- **WHEN** an authorized `POST /admin/log-level` request names a
  recognized level
- **THEN** the service's application log level changes immediately and
  the response confirms the newly active level

### Requirement: An unrecognized level is rejected
A request naming a level other than `DEBUG`, `INFO`, `WARNING`, or
`ERROR` SHALL be rejected with HTTP 400, and the running log level SHALL
remain unchanged.

#### Scenario: Unrecognized level name
- **WHEN** an authorized `POST /admin/log-level` request names a level
  that is not one of the recognized levels
- **THEN** the service rejects the request with HTTP 400 and the running
  log level is unchanged

### Requirement: The admin token is never logged
The configured `ADMIN_API_TOKEN` and any bearer token presented on a
request SHALL NOT appear in application logs at any log level, including
on a rejected (401) request.

#### Scenario: Rejected request with an invalid token
- **WHEN** a `POST /admin/log-level` request is rejected for an invalid
  bearer token
- **THEN** the rejection is logged without including the presented token
  value or the configured `ADMIN_API_TOKEN`
