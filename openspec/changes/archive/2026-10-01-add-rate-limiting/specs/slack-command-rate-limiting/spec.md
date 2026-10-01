# Spec Delta

## Purpose

Protects `/trust`, `/revoke`, and `/trust-status` from being spammed by a
single Slack user issuing commands in rapid succession, by rejecting
excess commands per issuing user — sharing one limit across all three
commands — with a visible Slack response and a logged violation.

## ADDED Requirements

### Requirement: Commands are rate limited per issuing Slack user
The system SHALL track incoming `/trust`, `/revoke`, and `/trust-status`
commands per issuing Slack user ID, sharing a single counter across all
three commands, and enforce the configured limit
(`rate_limiting.slack_commands.max_requests` per
`rate_limiting.slack_commands.window_seconds`).

#### Scenario: Commands within the limit
- **WHEN** a Slack user has issued fewer commands (of any of the three
  types, combined) than the configured maximum within the current window
- **THEN** the command proceeds to its normal authorization checks and
  processing

#### Scenario: Limit is shared across commands
- **WHEN** a Slack user issues a mix of `/trust`, `/revoke`, and
  `/trust-status` commands
- **THEN** all of them count against the same shared limit, not three
  independent limits

### Requirement: Exceeding the limit produces a visible rejection
A Slack user who has exceeded the configured limit SHALL have their
command rejected before its normal authorization checks, with a visible
Slack response explaining they are rate limited — unlike the silent
rejection used for an unauthorized-channel command.

#### Scenario: Slack user exceeds the configured limit
- **WHEN** a Slack user has already issued `max_requests` commands within
  the current `window_seconds` window
- **THEN** the service responds in Slack with a message indicating the
  user is rate limited, and does not evaluate the command against the
  rules engine or any read-only lookup

### Requirement: Violations are logged
Every rejected-for-rate-limit command SHALL be logged at WARNING level or
above, identifying the issuing Slack user.

#### Scenario: A command is rejected for exceeding the rate limit
- **WHEN** the service responds with a rate-limited message for exceeding
  the rate limit
- **THEN** a WARNING-level (or higher) log entry is emitted identifying
  the Slack user who was rate limited
