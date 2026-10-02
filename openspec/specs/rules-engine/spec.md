# rules-engine Specification

## Purpose

Evaluates incoming trigger events against declaratively-configured rules and
dispatches their actions, so that community-specific access logic lives
entirely in `rules.yaml` rather than in service code.

## Requirements

### Requirement: Rules are re-read from disk on every trigger event
The system SHALL re-read and re-parse `rules.yaml` from the mounted config
directory each time a trigger event is evaluated, so that rule changes take
effect immediately without a service restart.

#### Scenario: Rule added between two events
- **WHEN** an operator adds a new rule to `rules.yaml` after the service has
  started, and a trigger event is then received
- **THEN** the new rule is included in evaluation for that event, without
  requiring a restart

### Requirement: A rule matches when any of its triggers matches
Within a single rule, the system SHALL use OR logic across that rule's
triggers: the rule is considered matched if at least one of its triggers
matches the incoming event.

#### Scenario: Rule with multiple triggers, one matches
- **WHEN** a rule lists more than one trigger and the incoming event matches
  at least one of them
- **THEN** the rule is treated as matched and its actions are executed

### Requirement: Disabled rules are never evaluated
The system SHALL skip any rule whose `enabled` field is `false`: its triggers
are not checked and its actions are never executed.

#### Scenario: Disabled rule would otherwise match
- **WHEN** a rule has `enabled: false` and its trigger would otherwise match
  the incoming event
- **THEN** the rule's actions do not execute and no audit record is produced
  for that rule

### Requirement: All matching rules execute on a single event
The system SHALL evaluate every enabled rule against an incoming trigger
event and execute the actions of every rule that matches, not only the
first match.

#### Scenario: Two independent rules match the same event
- **WHEN** an incoming event satisfies the triggers of two separate enabled
  rules
- **THEN** the actions of both rules are executed

### Requirement: Trigger and action dispatch is generic by type
The system SHALL dispatch a trigger's matching logic and an action's
execution logic based on the `type` field of that trigger/action, through a
lookup that can be extended with new types without modifying the rule
loading or evaluation logic itself.

#### Scenario: Adding a new trigger or action type
- **WHEN** a new trigger or action type is registered with the engine (e.g. a
  future `github_contribution` trigger)
- **THEN** existing rules and the engine's loading/evaluation logic continue
  to function unchanged

### Requirement: Every attempted action is audited
The system SHALL produce exactly one audit log entry for every action
execution it attempts as a result of a matched rule, whether the outcome
is success, a no-op, a failure, or — while dry-run mode is active — a
simulated (dry-run) outcome.

#### Scenario: Matched rule's action is attempted
- **WHEN** a rule matches an event and its action is executed
- **THEN** an audit log entry is recorded noting the rule name, the trigger
  that matched, the action attempted, and the outcome

#### Scenario: Matched rule's action is attempted during dry-run
- **WHEN** a rule matches an event while dry-run mode is active and its
  action is evaluated
- **THEN** an audit log entry is recorded noting the rule name, the
  trigger that matched, the action that would have been attempted, and
  a dry-run outcome
