# Spec Delta

## MODIFIED Requirements

### Requirement: Commands are rate limited per issuing Slack user
The system SHALL track incoming `/trust`, `/trust-revoke`, and
`/trust-status` commands per issuing Slack user ID, sharing a single
counter across all three commands, and enforce the configured limit
(`rate_limiting.slack_commands.max_requests` per
`rate_limiting.slack_commands.window_seconds`).

#### Scenario: Commands within the limit
- **WHEN** a Slack user has issued fewer commands (of any of the three
  types, combined) than the configured maximum within the current window
- **THEN** the command proceeds to its normal authorization checks and
  processing

#### Scenario: Limit is shared across commands
- **WHEN** a Slack user issues a mix of `/trust`, `/trust-revoke`, and
  `/trust-status` commands
- **THEN** all of them count against the same shared limit, not three
  independent limits
