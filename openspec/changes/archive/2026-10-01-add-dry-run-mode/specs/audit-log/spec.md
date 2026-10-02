# Spec Delta

## MODIFIED Requirements

### Requirement: Status is constrained to known outcome values
Every `audit_log` row's `status` column SHALL be one of `success`,
`no_change`, `failure`, or `dry_run`.

#### Scenario: Row is written
- **WHEN** an audit row is written for any action attempt
- **THEN** its `status` value is exactly one of `success`, `no_change`,
  `failure`, or `dry_run`

#### Scenario: Row is written while dry-run mode is active
- **WHEN** an audit row is written for an action evaluated while dry-run
  mode is active
- **THEN** its `status` value is `dry_run`, regardless of what the
  outcome would have been had the action actually executed
