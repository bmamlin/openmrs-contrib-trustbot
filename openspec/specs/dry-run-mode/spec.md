# dry-run-mode Specification

## Purpose

Lets an operator run the rules engine against real trigger events —
Discourse trust-level changes, Slack `/trust` and `/revoke` commands —
without making any actual change to Keycloak, so `rules.yaml` changes and
new wiring can be verified safely before being trusted in production.

## Requirements

### Requirement: Dry-run mode is a single process-wide setting
The system SHALL support a `dry_run` setting that is either on or off for
the whole running process, applying uniformly to every trigger path
(the Discourse webhook and every Slack command that reaches the rules
engine). There is no per-request or per-rule override.

#### Scenario: Dry-run enabled
- **WHEN** the service starts with dry-run mode enabled
- **THEN** every subsequent trigger event — Discourse webhook or Slack
  command — is evaluated under dry-run semantics, with no exceptions

### Requirement: No external system is mutated while dry-run is active
While dry-run mode is active, a matched rule's actions SHALL be fully
evaluated (including querying current state from the relevant external
system, e.g. current Keycloak group membership) and their outcome SHALL
be recorded to the audit log, but SHALL NOT make any actual change to
that external system.

#### Scenario: Action would normally add a user to a group
- **WHEN** dry-run mode is active and a matched rule's action would, in
  normal operation, add the target OpenMRS ID to one or more Keycloak
  groups
- **THEN** the action queries Keycloak for the user's current groups,
  computes which groups it would add, records that outcome to the audit
  log, and does not call Keycloak to actually add the user to any group

#### Scenario: Action would normally be a no-op
- **WHEN** dry-run mode is active and the target OpenMRS ID already
  satisfies the action's intended end state (e.g. already has every
  group a grant action would add)
- **THEN** the recorded outcome's status is still the dry-run status
  (per "Dry-run outcomes are distinguishable in the audit log" below),
  but its detail states that no change would have occurred even outside
  dry-run mode, rather than implying a change was simulated

### Requirement: Dry-run outcomes are distinguishable in the audit log
Every audit log row written while dry-run mode is active SHALL be
identifiable as a simulation, never indistinguishable from a row
representing a real, applied change.

#### Scenario: Audit row written during dry-run
- **WHEN** an action is evaluated while dry-run mode is active
- **THEN** the resulting audit log row's status clearly identifies it as
  a dry-run outcome, distinct from `success`, `no_change`, or `failure`

### Requirement: Dry-run is configured at startup, with an environment override
The system SHALL read dry-run mode from `config.yaml`'s `dry_run` field at
startup (default `false`), optionally overridden by a `DRY_RUN`
environment variable (`true`/`false`, case-insensitive). A blank or unset
`DRY_RUN` SHALL fall back to the configured value rather than being
treated as `false`.

#### Scenario: No environment override
- **WHEN** `DRY_RUN` is unset or blank
- **THEN** the service uses `config.yaml`'s `dry_run` value

#### Scenario: Environment override present
- **WHEN** `DRY_RUN` is set to `true` or `false` (any case)
- **THEN** the service uses that value regardless of `config.yaml`'s
  `dry_run` setting

### Requirement: Slack commands disclose dry-run in their response
A `/trust` or `/revoke` command that passes authorization and is
evaluated while dry-run mode is active SHALL receive a response that
clearly states no real change was made, rather than the normal
success/no-change wording.

#### Scenario: /trust evaluated during dry-run
- **WHEN** a `/trust <openmrs-id>` command passes authorization checks
  while dry-run mode is active
- **THEN** the Slack response states that the grant was simulated and no
  real change was made

#### Scenario: /revoke evaluated during dry-run
- **WHEN** a `/revoke <openmrs-id>` command passes authorization checks
  while dry-run mode is active
- **THEN** the Slack response states that the revocation was simulated
  and no real change was made
