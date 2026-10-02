# audit-log Specification

## Purpose

Provides a durable, append-only record of every access-provisioning action
the system attempts, so ITSM can review what happened, when, and why.

## Requirements

### Requirement: Every attempted action is recorded
The system SHALL append exactly one row to the `audit_log` table for every
rule action it attempts, regardless of whether the outcome was a success,
a no-op, or a failure.

#### Scenario: Action attempted
- **WHEN** a matched rule's action is executed
- **THEN** one `audit_log` row is written capturing timestamp (ISO 8601
  UTC), `openmrs_id`, `trigger`, `trigger_src`, `rule_name`, `action`,
  `action_detail`, `status`, and `detail`

### Requirement: The audit log is append-only
The system SHALL only INSERT new rows into `audit_log`. It SHALL NOT UPDATE
or DELETE any existing row.

#### Scenario: Any audit write
- **WHEN** the system writes to the audit log for any reason
- **THEN** the write is an INSERT of a new row; no existing row is modified
  or removed

### Requirement: Audit data persists across service restarts
The audit database SHALL be stored on the host-mounted `/data` volume so
that its contents survive container restarts and redeployments.

#### Scenario: Service restarts
- **WHEN** the service container is restarted
- **THEN** `audit_log` rows written before the restart are still present
  and queryable afterward

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
