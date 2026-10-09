# Tasks

## 1. Rename the command in code, and its own tests

- [x] 1.1 In `src/integrations/slack.py`, change `@app.command("/revoke")` to
  `@app.command("/trust-revoke")`, and update every user-facing string in
  `_handle_revoke`/`_format_revoke_response` and the module docstring that
  reads `/revoke` (usage message, "no rule configured" message, the two
  WARNING log messages, the docstring's command list) to `/trust-revoke`.
  Do not rename `_handle_revoke`, `_format_revoke_response`,
  `handle_revoke_command`, or anything referencing the
  `slack_revoke_command` trigger type. Verify with
  `grep -n "/revoke" src/integrations/slack.py` returning no matches.
- [x] 1.2 In `src/triggers/slack.py`, update the module docstring and the
  `build_revoke_event` docstring's mentions of `/revoke` to
  `/trust-revoke`. Do not rename `build_revoke_event`, `matches_revoke`,
  or the `slack_revoke_command` trigger/event type strings they use.
  Verify with `grep -n "/revoke" src/triggers/slack.py` returning no
  matches.
- [x] 1.3 Update the literal `/revoke` command string in
  `tests/unit/integrations/test_slack.py` (the `matcher.func({"command":
  "/revoke"})` call) to `/trust-revoke`, then verify with
  `pytest tests/unit/integrations/test_slack.py`.
- [x] 1.4 Update `tests/security/test_slack_revoke_command.py`'s module
  docstring and literal `"/revoke"` command field to `/trust-revoke`,
  then verify with `pytest tests/security/test_slack_revoke_command.py`.
- [x] 1.5 Update `tests/integration/test_slack_revoke_flow.py`'s module
  docstring and any literal `/revoke` command string to `/trust-revoke`,
  then verify with `pytest tests/integration/test_slack_revoke_flow.py`.
- [x] 1.6 Update `tests/integration/test_slack_trust_status_flow.py`'s
  module docstring mention of `/revoke` to `/trust-revoke`, then verify
  with `pytest tests/integration/test_slack_trust_status_flow.py`.
- [x] 1.7 Update `tests/integration/test_slack_rate_limiting.py`'s module
  docstring and literal `/revoke` command strings (including the
  `invoke(middleware, user_id="U1", command="/revoke")` call) to
  `/trust-revoke`, then verify with
  `pytest tests/integration/test_slack_rate_limiting.py`.

## 2. Update rules.yaml data (comments and rule name only)

- [x] 2.1 In `config/rules.example.yaml`, update the comment "Manually
  revoke community edit access via Slack /revoke command." and the rule
  `name: "Revoke community edit access (manual /revoke)"` to say
  `/trust-revoke` instead. Leave the `type: slack_revoke_command` trigger
  line itself unchanged.
- [x] 2.2 Update the matching comment and rule `name` in the user's own
  `config/rules.yaml` (gitignored, not tracked by git) the same way, for
  consistency with the example file.
- [x] 2.3 Update `tests/unit/engine/test_loader.py`'s assertion
  `"Revoke community edit access (manual /revoke)" in names` to match the
  new rule name, then verify with `pytest tests/unit/engine/test_loader.py`.

## 3. Update documentation

- [x] 3.1 Update every `/revoke` mention in `openspec/specs/overview.md`
  (the Slack commands bullet, the trigger-type table row, the command
  list, the channel-restriction requirement, and the two "Resolved"
  notes) to `/trust-revoke`. Verify with
  `grep -n "/revoke" openspec/specs/overview.md` returning no matches.
- [x] 3.2 Update the comment and rule `name` in
  `openspec/specs/config-schema.md`'s rules.yaml example (mirroring task
  2.1) to `/trust-revoke`. Verify with
  `grep -n "/revoke" openspec/specs/config-schema.md` returning no
  matches.
- [x] 3.3 Update both `/revoke` mentions in `README.md` (the endpoints
  table row and the Status section) to `/trust-revoke`. Verify with
  `grep -n "/revoke" README.md` returning no matches.
- [x] 3.4 Update every `/revoke` mention in `CLAUDE.md` (the bullet
  listing Slack slash commands, the "Current state" paragraph's command
  list and response-disclosure sentence, and the rate-limiting sentence)
  to `/trust-revoke`. Verify with `grep -n "/revoke" CLAUDE.md` returning
  no matches.

## 4. Final verification

- [x] 4.1 Run the full test suite with `pytest` and confirm every test
  passes.
- [x] 4.2 Run `grep -rn "/revoke" src/ tests/ README.md CLAUDE.md
  config/rules.example.yaml openspec/specs/*.md` and confirm the only
  remaining matches are internal identifiers that intentionally keep
  their name (`slack_revoke_command`, `keycloak_remove_groups`) or
  unrelated uses of the English words "revoke"/"revoked"/"revocation" —
  no remaining reference to the literal `/revoke` command.

## Workflow follow-up

- Archive this change once all tasks above are complete and reviewed.
- Commit the resulting code, test, and documentation changes.
- Tag and release v1.2.0, after confirming the user has updated the
  registered slash command in the Slack App's own configuration (outside
  this repo) to `/trust-revoke` to match.
