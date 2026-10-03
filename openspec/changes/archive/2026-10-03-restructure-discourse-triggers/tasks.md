# Tasks

## 1. Live verification (do first — gates task 5)

- [x] 1.1 Configure a test native webhook in Discourse's admin UI
      (Admin > API > Webhooks) pointed at an ngrok tunnel to
      `/webhook/discourse`, selecting the `user_promoted` and badge
      event categories. Trigger each (promote a test user's trust
      level; grant and revoke a test badge) and capture the raw
      request: headers (`X-Discourse-Event-Type`,
      `X-Discourse-Event-Signature` format) and full JSON body for
      each of the three event types. Confirm whether
      `user_badge_granted`/`user_badge_revoked` resolve a `username`
      directly or only a numeric user ID (per design.md's flagged
      risk) — if only an ID, descope badge-event support from this
      change (keep `user_promoted` and the Workflow path) and note
      the finding in a follow-up proposal.
      DONE, with two findings that changed the design:
      (1) `X-Discourse-Event-Type` is only the coarse category —
      `user_badge_granted`/`user_badge_revoked` both send
      `X-Discourse-Event-Type: user_badge`; the actual dispatch name
      must come from `X-Discourse-Event` instead (confirmed
      `user_promoted` happens to match in both headers, masking this
      until badge payloads were captured). Every reference to
      `X-Discourse-Event-Type` as the dispatch header, across code,
      tests, and specs, was corrected to `X-Discourse-Event`.
      (2) Badge payloads confirmed to carry only a numeric `user_id`,
      never a `username` — per explicit direction, NOT descoped;
      instead the parsers accept a forward-compatible top-level
      `username` and raise (HTTP 400, logged) when absent, so these
      triggers fail loudly today and start working automatically once
      Discourse adds the field (open Meta request), with no code
      change needed here.

## 2. Config and model changes

- [x] 2.1 In `src/config.py`, remove `DiscourseWebhookConfig`;
      `DiscourseConfig` becomes `{base_url: str}` only. Verify
      `tests/unit/test_config.py` still passes with the simplified
      shape (drop any case that set `discourse.webhook.*`).
- [x] 2.2 In `src/engine/models.py`, add `name: str | None = None` to
      `TriggerEvent`. Verify `tests/unit/engine/test_models.py` gains a
      case constructing a `TriggerEvent` with `name` set, and update
      its existing `discourse_trust_level` example trigger to
      `{type: "workflow", name: "trusted"}`.

## 3. New trigger modules

- [x] 3.1 Delete `src/triggers/discourse.py`. Create
      `src/triggers/discourse_workflow.py`: `matches(trigger, event)`
      (`trigger.type == "workflow" and event.type == "workflow" and
      trigger.name == event.name`) and `build_event(workflow_name,
      payload, *, discourse_base_url) -> TriggerEvent` (requires a
      top-level `username` key, raises `ValueError` if absent; passes
      the rest of the payload through as `TriggerEvent.payload`).
      Verify a new `tests/unit/triggers/test_discourse_workflow.py`
      covers: matching by name, non-matching on a different name,
      building an event from a payload with `username`, and raising on
      a payload missing `username`.
- [x] 3.2 Create `src/triggers/discourse_webhook.py`: the same
      `matches(trigger, event)` shape for `"webhook"`, plus
      `PAYLOAD_PARSERS: dict[str, Callable[[dict], tuple[str, dict]]]`
      with entries for `user_promoted`, `user_badge_granted`, and
      `user_badge_revoked` (field names/nesting per task 1.1's live
      capture), and `build_event(event_name, payload, *,
      discourse_base_url) -> TriggerEvent | None` (returns `None` if
      `event_name not in PAYLOAD_PARSERS`). Verify a new
      `tests/unit/triggers/test_discourse_webhook.py` covers: matching
      by name, each of the three parsers against a realistic captured
      payload, and `build_event()` returning `None` for an unregistered
      event name.
      DONE, with the task 1.1 corrections applied: `user_promoted`
      resolves `username` from `payload["user_promoted"]`; the two
      badge parsers accept a forward-compatible top-level `username`
      and raise `ValueError` (not return `None`) when absent — a real
      error, not silent-unsupported, per design.md. 10 tests passing,
      including both the forward-compatible shape and the real
      (no-username) captured payload for each badge event.
- [x] 3.3 Delete `tests/unit/triggers/test_discourse.py` (superseded by
      3.1/3.2's new test files).
- [x] 3.4 In `src/triggers/__init__.py`, replace the
      `discourse_trust_level` registration with
      `register_trigger("webhook", discourse_webhook.matches)` and
      `register_trigger("workflow", discourse_workflow.matches)`.

## 4. Webhook route

- [x] 4.1 Rewrite `src/api/webhooks.py`: `WebhookContext` drops
      `replay_window_seconds`/`workflow_name`, gains `webhook_secret`
      (native) alongside the renamed `workflow_secret` (existing
      Workflow secret, same value/purpose as today's `webhook_secret`
      param — rename for clarity now that there are two). The route
      handler: rate-limit check (unchanged) → check
      `X-Discourse-Event-Type` header first (native webhook branch:
      verify `X-Discourse-Event-Signature` against `webhook_secret`,
      403 on failure; call `discourse_webhook.build_event()`, respond
      200 with no action if it returns `None`; else evaluate+execute) →
      else check `X-Discourse-Workflow` header (workflow branch: verify
      `X-Discourse-Workflow-Secret` against `workflow_secret`, 403 on
      failure; call `discourse_workflow.build_event()`, 400 if it
      raises `ValueError`; else evaluate+execute) → else 400 (neither
      header present). `create_webhooks_router(...)`'s parameters
      updated to match (`webhook_secret`, `workflow_secret`,
      `discourse_base_url`, `audit_conn`, `rate_limiter`, `dry_run` —
      drop `replay_window_seconds`, `workflow_name`).
- [x] 4.2 Rewrite `tests/unit/api/test_webhooks.py` for the new
      branching: valid native-webhook signature + supported event type
      reaches the rules engine; valid native-webhook signature +
      unsupported event type returns 200 with no audit row; invalid
      native-webhook signature returns 403; valid workflow signature +
      payload with `username` reaches the rules engine; valid workflow
      signature + payload missing `username` returns 400; invalid
      workflow signature returns 403; neither header present returns
      400; rate limiting still short-circuits before any of the above
      (reuse the existing rate-limit test cases, adapted).
      The "supported event type reaches the rules engine" case was
      initially deferred (pending task 1.1); now added
      (`test_user_promoted_reaches_the_rules_engine`), plus
      `test_user_badge_granted_with_no_username_returns_400` for the
      real captured badge payload shape. 18 tests passing.

## 5. Wiring, example config, and docs

- [x] 5.1 In `src/main.py`, read `DISCOURSE_WEBHOOK_SECRET` (required,
      same fail-fast pattern as other required secrets); remove the
      `DISCOURSE_REPLAY_WINDOW_SECONDS` override logic entirely; update
      the `webhooks.create_webhooks_router(...)` call. Verify
      `tests/unit/test_main.py` still passes — delete its
      blank-`DISCOURSE_REPLAY_WINDOW_SECONDS`-env-var regression test
      (the env var no longer exists) and add `DISCOURSE_WEBHOOK_SECRET`
      to its fixtures.
- [x] 5.2 Update `config/config.example.yaml`: remove the
      `discourse.webhook` block entirely. Update `.env.example`: remove
      `DISCOURSE_REPLAY_WINDOW_SECONDS`, add `DISCOURSE_WEBHOOK_SECRET`
      (documented alongside `DISCOURSE_WORKFLOW_SECRET`).
- [x] 5.3 Update `config/rules.example.yaml`: replace the
      `discourse_trust_level` rule with
      `{type: workflow, name: "trusted"}` (same action). Add a second,
      commented-out example rule using
      `{type: webhook, name: "user_promoted"}` to document the native
      webhook pattern without changing live default behavior.
- [x] 5.4 Update `openspec/specs/config-schema.md`: mirror 5.2/5.3's
      changes in the documented `config.yaml`/`rules.yaml` blocks, and
      the Environment Variables Reference table (remove
      `DISCOURSE_REPLAY_WINDOW_SECONDS`, add `DISCOURSE_WEBHOOK_SECRET`,
      update `DISCOURSE_WORKFLOW_SECRET`'s description to note it is no
      longer scoped to one workflow name).
- [x] 5.5 Update `openspec/specs/overview.md`: remove or rewrite the
      three replay-protection mentions (§5.2, §6.3, the Open
      Questions "Resolved" note citing "replay attack protection") to
      reflect the deliberate removal and its rationale (idempotent
      actions), and update §6.5's security-test checklist bullet
      accordingly (drop "replay attacks on webhooks" from the expected
      test category list).
- [x] 5.6 Update `openspec/specs/repository-plan.md`'s file-tree comment
      (`discourse.py` → `discourse_webhook.py`/`discourse_workflow.py`)
      and its `DISCOURSE_WORKFLOW_SECRET` env var table row/add
      `DISCOURSE_WEBHOOK_SECRET`.
- [x] 5.7 Update `src/integrations/discourse.py`'s module docstring
      (references the now-removed `discourse_trust_level` trigger by
      name).
- [x] 5.8 Update `CLAUDE.md` and `README.md`: replace every mention of
      the single hardcoded Workflow/`discourse_trust_level` with the
      new `type: webhook`/`type: workflow` model; update README's
      "Set up a Discourse Workflow" and "Test the Discourse trust-level
      trigger" sections' env var references
      (`DISCOURSE_WORKFLOW_SECRET` unchanged, new
      `DISCOURSE_WEBHOOK_SECRET` documented, replay-window mentions
      removed); note that replay protection was deliberately removed.

## 6. Integration and security test collateral

- [x] 6.1 Rename `tests/integration/test_discourse_trust_level_flow.py`
      to `test_discourse_workflow_flow.py`, updating it to POST with
      `X-Discourse-Workflow: trusted` against the updated
      `config/rules.example.yaml`'s `{type: workflow, name: "trusted"}`
      rule, with the same successful-grant/no-op/no-match scenarios as
      today. Add a new `tests/integration/test_discourse_webhook_flow.py`
      covering the same shape for a `user_promoted` native webhook
      request against a `{type: webhook, name: "user_promoted"}` test
      rule.
      DONE: workflow-flow half (4 tests) and the webhook-flow half
      (`test_discourse_webhook_flow.py`, 3 tests, against a
      `user_promoted` test rule) both passing.
- [x] 6.2 Update `tests/security/test_discourse_webhook.py` for the new
      two-secret, two-header-scheme model (both an invalid native
      webhook signature and an invalid workflow signature are rejected
      before any processing, through the real app).
- [x] 6.3 Update the `CONFIG_YAML` fixtures and env var setup in
      `tests/security/test_rate_limiting.py`,
      `tests/security/test_dry_run_mode.py`,
      `tests/security/test_admin_log_level.py`,
      `tests/security/test_slack_trust_command.py`,
      `tests/security/test_slack_revoke_command.py`, and
      `tests/security/test_slack_trust_status_command.py`: remove the
      `discourse.webhook` block, add `DISCOURSE_WEBHOOK_SECRET` to each
      fixture's env vars (now required by `src/main.py`).

## 7. Full verification

- [x] 7.1 Run `pytest` and confirm every unit, integration, and
      security test — old and new — passes; run `python -m py_compile`
      over all changed files under `src/`; run `openspec validate
      --strict` against this change.
      DONE: 169/169 tests pass (5 consecutive full-suite runs, no
      flakiness), `py_compile` clean, `openspec validate --strict`
      valid.
