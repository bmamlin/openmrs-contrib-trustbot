# Spec Delta

## MODIFIED Requirements

### Requirement: Commands are restricted to the designated trusted channel
The system SHALL only act on `/trust` commands issued from the channel ID
configured as `slack.trusted_channel_id`. Commands from any other channel
SHALL be rejected silently (no action is taken and no response is sent)
and logged at WARNING level or above.

#### Scenario: Command issued from an unauthorized channel
- **WHEN** a `/trust <openmrs-id>` command is issued from a channel other
  than the configured trusted channel
- **THEN** the service takes no action, sends no response, and logs the
  rejection at WARNING level
