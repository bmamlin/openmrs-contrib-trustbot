# Spec Delta

## MODIFIED Requirements

### Requirement: Slack commands disclose dry-run in their response
A `/trust` or `/trust-revoke` command that passes authorization and is
evaluated while dry-run mode is active SHALL receive a response that
clearly states no real change was made, rather than the normal
success/no-change wording.

#### Scenario: /trust evaluated during dry-run
- **WHEN** a `/trust <openmrs-id>` command passes authorization checks
  while dry-run mode is active
- **THEN** the Slack response states that the grant was simulated and no
  real change was made

#### Scenario: /revoke evaluated during dry-run
- **WHEN** a `/trust-revoke <openmrs-id>` command passes authorization
  checks while dry-run mode is active
- **THEN** the Slack response states that the revocation was simulated
  and no real change was made
