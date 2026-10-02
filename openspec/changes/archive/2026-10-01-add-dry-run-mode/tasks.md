# Tasks

## 1. Config

- [x] 1.1 Add `dry_run: bool = False` to `ServiceConfig` in `src/config.py`;
      verify `tests/unit/test_config.py` (or wherever `ServiceConfig`
      parsing is tested) gains a case confirming it defaults to `False`
      when absent from `config.yaml` and parses correctly when set `true`.
      Update `config/config.example.yaml` with a commented `dry_run: false`
      entry and `.env.example` with a commented `DRY_RUN=` line (mirroring
      `LOG_LEVEL`'s documentation style).

## 2. Engine and Keycloak plumbing

- [x] 2.1 In `src/engine/models.py`, add `"dry_run"` to
      `ActionResult.status`'s `Literal`.
- [x] 2.2 In `src/engine/evaluator.py`, change `execute_rule()`'s
      signature to `execute_rule(rule, event, *, conn, dry_run: bool =
      False)` and pass `dry_run` as a third positional argument to every
      `executor(action, event, dry_run)` call (the "unknown action type"
      branch is unaffected — it never calls an executor). Update the
      `ACTION_EXECUTORS` type alias to
      `Callable[[Action, TriggerEvent, bool], ActionResult]`.
- [x] 2.3 In `src/integrations/keycloak.py`, add `dry_run: bool = False`
      to `KeycloakClient.add_user_to_groups`/`remove_user_from_groups`;
      when `True`, skip the `group_user_add`/`group_user_remove` call
      inside the loop but still return the same list of group names that
      would have been added/removed. Verify
      `tests/unit/integrations/test_keycloak.py` gains cases for both
      methods: dry-run with groups to add/remove returns the expected
      list without the mock client's add/remove call being made;
      dry-run with nothing to add/remove behaves identically to normal
      mode (empty list, no calls).
- [x] 2.4 In `src/actions/keycloak.py`, add a `dry_run: bool` parameter
      to `add_groups`/`remove_groups` (matching the new
      `ACTION_EXECUTORS` signature), pass it to the `KeycloakClient`
      call, and set `status="dry_run"` instead of `"success"`/
      `"no_change"` when `dry_run` is `True` — keep the existing
      `detail`/`action_detail` wording (just a different status).
      Verify `tests/unit/actions/test_keycloak.py` gains cases: dry-run
      with groups to add/remove returns `status="dry_run"` with the
      would-be groups in `detail`/`action_detail`; dry-run with nothing
      to add/remove still returns `status="dry_run"` (never
      `"no_change"`) with detail noting no change would occur; the
      `UserNotFoundError`/`KeycloakConnectionError` failure paths are
      unaffected by `dry_run` (still `status="failure"`).
- [x] 2.5 Verify `tests/unit/engine/test_evaluator.py` gains a case:
      `execute_rule(..., dry_run=True)` passes `True` through to a
      registered test executor and the resulting audit row's `status`
      is whatever the executor returned (confirming the engine itself
      doesn't special-case dry-run, just threads the flag).
      Discovered while implementing: `src/audit/db.py: record_event()`
      has its own hardcoded status allow-list
      (`"success"`/`"no_change"`/`"failure"`) that design.md didn't
      mention — extended it to accept `"dry_run"` too (required for the
      already-specified "dry-run outcomes are distinguishable in the
      audit log" behavior to work at all); added
      `test_record_event_accepts_dry_run_status` to
      `tests/unit/audit/test_db.py`.

## 3. Wiring into both trigger entry points

- [x] 3.1 In `src/api/webhooks.py`, add `dry_run: bool` to
      `WebhookContext` and `create_webhooks_router(...)`'s parameters;
      pass `context.dry_run` to the `evaluator.execute_rule(...)` call.
      Verify `tests/unit/api/test_webhooks.py` gains a case: with
      `dry_run=True` and a valid request, the resulting audit row's
      `status` is `"dry_run"` (requires a real `rules.yaml` — mirror how
      `tests/integration/test_discourse_trust_level_flow.py` sets
      `RULES_PATH`, or add this case there instead if simpler).
      Added there instead, per the task's own suggestion, since the
      fixture already has a real rules.yaml wired up.
- [x] 3.2 In `src/integrations/slack.py`, add `dry_run: bool` to
      `SlackContext`, `create_slack_app(...)`'s parameters, and pass
      `context.dry_run` to both `_handle_trust`/`_handle_revoke`'s
      `evaluator.execute_rule(...)` calls.
- [x] 3.3 Add a dry-run branch to `_format_response`/
      `_format_revoke_response` (checked before the existing
      failure/no-change/success checks): when every outcome's status is
      `"dry_run"`, respond with wording that clearly states the grant/
      revoke was simulated and no real change was made. Verify
      `tests/integration/test_slack_trust_flow.py` and
      `test_slack_revoke_flow.py` each gain a case: with `dry_run=True`
      on the `SlackContext`, the response states the action was
      simulated, the audit row's status is `"dry_run"`, and the mocked
      Keycloak client's `add_user_to_groups`/`remove_user_from_groups`
      is never called.
- [x] 3.4 In `src/main.py`, read `DRY_RUN` via
      `os.environ.get("DRY_RUN", "").strip().lower()`; resolve to a
      boolean per design.md's allow-list (`"true"`/`"1"`/`"yes"`/`"on"`
      → `True`; blank → fall back to `config.dry_run`; anything else →
      `False`); pass the resolved value into both
      `webhooks.create_webhooks_router(...)` and `create_slack_app(...)`.
      Verify `tests/unit/test_main.py` still passes, plus a new case
      confirming a blank `DRY_RUN` env var falls back to `config.yaml`'s
      `dry_run` value (mirroring the existing
      `DISCOURSE_REPLAY_WINDOW_SECONDS` blank-env-var regression test).

## 4. Security-focused test

- [x] 4.1 Add `tests/security/test_dry_run_mode.py`, exercising both
      entry points through the real app (`src.main`, `dry_run: true` in
      the test's `config.yaml`): a validly-signed Discourse webhook
      request and a validly-authorized `/trust` command each produce a
      `dry_run` audit row and no call to the mocked Keycloak client's
      mutating methods.
      Corrected while implementing: the mock stands in for the whole
      `KeycloakClient`, and `add_user_to_groups`/`remove_user_from_groups`
      themselves are still called (they do the live membership read) —
      it's the *internal* `group_user_add`/`group_user_remove` calls that
      are skipped, already verified at that level in
      `tests/unit/integrations/test_keycloak.py`. This test instead
      asserts the mock was called with `dry_run=True`, confirming the
      flag reached it end to end, plus the `dry_run` audit row.
      Also discovered: slack-bolt dispatches command listeners on a
      background thread by default (`process_before_response=False`) —
      the HTTP response returns as soon as `ack()` is called, racing
      with `_handle_trust()`'s audit write. Fixed by polling briefly for
      the audit row instead of asserting immediately after the response
      (confirmed with 10 consecutive full-suite runs, previously flaky
      about 1 in 4).

## 5. Docs

- [x] 5.1 Update `src/audit/schema.sql`'s `status` column comment to
      list `dry_run` alongside the existing three values.
- [x] 5.2 Update `openspec/specs/config-schema.md`'s documented
      `config.yaml` with the new top-level `dry_run: false` field and
      its `DRY_RUN` environment variable override, matching the style
      already used for `logging.level`/`LOG_LEVEL`.
- [x] 5.3 Update `CLAUDE.md`'s "Current state" note: dry-run mode is no
      longer the one remaining stub — note it's implemented, and that
      every item from the spec's Functional/Security Requirements
      checklists is now built. Update `README.md`'s "Status" section to
      match, and add a short "Test dry-run mode" manual-testing
      subsection describing how to set `DRY_RUN=true` and verify via
      `/trust` that no Keycloak change occurs.

## 6. Full verification

- [x] 6.1 Run `pytest` and confirm every unit, integration, and security
      test — old and new — passes; run `python -m py_compile` over all
      changed files under `src/`.
