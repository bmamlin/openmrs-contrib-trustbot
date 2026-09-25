# Tasks

## 1. Keycloak integration + action

- [x] 1.1 Implement `src/integrations/keycloak.py: KeycloakClient.remove_user_from_groups()`,
      mirroring `add_user_to_groups()`: query the user's current groups
      live, remove only the groups from the given list that the user
      actually has (idempotent), with the same single-retry-then-raise
      behavior on `KeycloakConnectionError`; verify
      `tests/unit/integrations/test_keycloak.py` gains cases covering:
      only-current-groups are removed (extra listed groups the user
      doesn't have are skipped), and the retry-once behavior (mirroring
      the existing `add_user_to_groups` retry test).
- [x] 1.2 Implement `src/actions/keycloak.py: remove_groups()` returning
      an `ActionResult`, mirroring `add_groups()`: `no_change` if the
      user already lacks every target group, `success` (with
      `action_detail` as a JSON list of groups actually removed)
      otherwise, and `failure` with a message identifying the user if the
      OpenMRS ID doesn't exist in Keycloak, or "Unable to reach Keycloak.
      Please try again later." on a connectivity failure; verify
      `tests/unit/actions/test_keycloak.py` gains the three-outcome
      coverage for `remove_groups()` mirroring the existing `add_groups()`
      tests.

## 2. Rules engine registration

- [x] 2.1 Register `"keycloak_remove_groups"` in
      `src/actions/__init__.py: register_all()` alongside the existing
      `"keycloak_add_groups"` registration; verify a unit test (extend
      `tests/unit/engine/test_evaluator.py::test_registries_are_populated_on_import`
      or add an adjacent assertion) confirms
      `"keycloak_remove_groups" in evaluator.ACTION_EXECUTORS` after
      import.

## 3. Slack integration + trigger

- [x] 3.1 Implement `src/triggers/slack.py: matches_revoke()` (mirrors
      `matches_trust()` — a type check, since MVP has no extra per-rule
      fields on this trigger) and a new `build_revoke_event()` (mirrors
      `build_trust_event()`: same channel-restriction check against
      `trusted_channel_id`, constructs a `TriggerEvent` with
      `type="slack_revoke_command"`); verify
      `tests/unit/triggers/test_slack.py` gains cases mirroring the
      existing `build_trust_event` tests: valid channel builds an event,
      wrong channel returns `None`, whitespace in the target id is
      stripped.
- [x] 3.2 Register `"slack_revoke_command"` in
      `src/triggers/__init__.py: register_all()` alongside the existing
      `"slack_trust_command"` registration; verify a unit test confirms
      `"slack_revoke_command" in evaluator.TRIGGER_MATCHERS` after import
      (same test location as task 2.1).
- [x] 3.3 In `src/integrations/slack.py`, register a `/revoke` command
      listener on the existing `App` (alongside `/trust`, same
      `SlackContext`), add a `_handle_revoke()` mirroring `_handle_trust()`
      (uses `build_revoke_event()` instead of `build_trust_event()`), and
      a `_format_revoke_response()` mirroring `_format_response()` but
      with revoke-appropriate wording ("has been revoked" /
      "is already not trusted" / "Could not revoke access to ..."); verify
      `tests/unit/integrations/test_slack.py` gains a case confirming the
      returned `App` has a registered `/revoke` command listener
      (mirroring the existing `/trust` assertion), and
      `tests/integration/test_slack_revoke_flow.py` (new, mirroring
      `test_slack_trust_flow.py`) exercises the full path with a mocked
      Keycloak client for: a successful revoke, a no-op revoke (already
      not trusted), an unknown OpenMRS ID, and a wrong-channel command
      producing no response and no audit row.

## 4. Security-focused tests

- [x] 4.1 Add `tests/security/test_slack_revoke_command.py`, mirroring
      `test_slack_trust_command.py`: a request with an invalid Slack
      signature is rejected before any Keycloak or audit call happens,
      and a validly-signed request from an unauthorized channel results
      in no rule-engine action and no visible Slack response, per the
      `slack-revoke-command` spec's authorization requirements; verify
      the tests pass under `pytest`.

## 5. Docs

- [x] 5.1 Update `CLAUDE.md`'s "Current state" note to include `/revoke`
      among the implemented commands (it currently lists `/revoke` under
      what remains stubbed); verify by re-reading the file against the
      actual final behavior.

## 6. Full verification

- [x] 6.1 Run `pytest` and confirm every unit, integration, and security
      test — old and new — passes; run `python -m py_compile` over all
      changed files under `src/`.
