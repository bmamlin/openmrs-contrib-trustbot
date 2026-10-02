# Spec Delta

## MODIFIED Requirements

### Requirement: Every attempted action is audited
The system SHALL produce exactly one audit log entry for every action
execution it attempts as a result of a matched rule, whether the outcome
is success, a no-op, a failure, or — while dry-run mode is active — a
simulated (dry-run) outcome.

#### Scenario: Matched rule's action is attempted
- **WHEN** a rule matches an event and its action is executed
- **THEN** an audit log entry is recorded noting the rule name, the
  trigger that matched, the action attempted, and the outcome

#### Scenario: Matched rule's action is attempted during dry-run
- **WHEN** a rule matches an event while dry-run mode is active and its
  action is evaluated
- **THEN** an audit log entry is recorded noting the rule name, the
  trigger that matched, the action that would have been attempted, and
  a dry-run outcome
