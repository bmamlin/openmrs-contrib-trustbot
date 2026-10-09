# Proposal

## Why

The three Slack slash commands do not share a consistent naming pattern:
`/trust`, `/revoke`, `/trust-status`. Now that the commands are in active
use, the standalone `/revoke` is both inconsistent with the `/trust*`
family and more likely to be issued by accident, since it reads as a
plausible generic word rather than a Trust-Bot-specific command.
Renaming it to `/trust-revoke` makes all three commands follow the same
`/trust*` pattern and reduces the chance of an accidental revocation.

## What Changes

- **BREAKING**: The Slack slash command `/revoke <openmrs-id>` is renamed
  to `/trust-revoke <openmrs-id>`. The Slack App's own registered slash
  command is updated separately, outside this repository, by the user.
- All user-facing strings that mention `/revoke` (usage messages, error
  messages, log messages) change to `/trust-revoke`.
- No change to behavior: signature verification, channel restriction,
  rule evaluation, response wording logic, dry-run handling, and audit
  capture all stay exactly as specified — only the command name changes.
- No change to internals: the trigger type name `slack_revoke_command`,
  the rules engine, and `rules.yaml`'s `type: slack_revoke_command`
  trigger syntax are unaffected and require no edits to `rules.yaml` or
  `rules.example.yaml` rule definitions (only their comments, which
  mention the old command name).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `slack-revoke-command`: every requirement and scenario currently
  worded around `/revoke <openmrs-id>` is reworded around
  `/trust-revoke <openmrs-id>`; no requirement's behavior changes.
- `dry-run-mode`: the "evaluated during dry-run" scenario and
  surrounding text reference `/revoke` and need the same rewording.
- `slack-command-rate-limiting`: the shared-rate-limit requirements
  listing `/trust`, `/revoke`, `/trust-status` need the same rewording.

## Impact

- **Code**: `src/integrations/slack.py` (command registration string and
  its usage/error/log message strings), `src/triggers/slack.py`
  (docstring mentions only — the function names and trigger type stay
  `slack_revoke_command`/unchanged).
- **Tests**: every test asserting the literal `/revoke` command string or
  its usage/error text (`tests/unit/integrations/test_slack.py`,
  `tests/security/test_slack_revoke_command.py`,
  `tests/integration/test_slack_revoke_flow.py`,
  `tests/integration/test_slack_trust_status_flow.py`,
  `tests/integration/test_slack_rate_limiting.py`,
  `tests/unit/engine/test_loader.py` if it references the comment text).
- **Docs**: `README.md`, `CLAUDE.md`, `openspec/specs/overview.md`,
  `openspec/specs/config-schema.md`, and the comments (not the trigger
  syntax) in `config/rules.example.yaml` and the user's own
  `config/rules.yaml`.
- **External**: the user updates the registered slash command in the
  Slack App's own configuration; this repo cannot do that for them.
- **Release**: ships as v1.2.0 once applied and tested.
