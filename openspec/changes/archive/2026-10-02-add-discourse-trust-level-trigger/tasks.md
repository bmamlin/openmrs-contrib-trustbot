# Tasks

## 1. Config and environment variable updates

- [x] 1.1 Rename `DISCOURSE_WEBHOOK_SECRET` to `DISCOURSE_WORKFLOW_SECRET`
      in `.env.example` and `openspec/specs/config-schema.md`'s
      Environment Variables Reference table, updating the description to
      reflect it's the secret shared with the Discourse Workflow's Code
      step (not Discourse's native webhook signing); verify by grepping
      the repo for `DISCOURSE_WEBHOOK_SECRET` and confirming zero
      remaining references.
- [x] 1.2 Add `discourse.webhook.workflow_name` to `src/config.py`'s
      `DiscourseWebhookConfig` (required field, no default — a
      misconfigured/missing value should fail config loading rather than
      silently accept every workflow name) and to
      `config/config.example.yaml` / `openspec/specs/config-schema.md`'s
      documented schema, with a comment explaining it's the label chosen
      when configuring the Discourse Workflow, not a Discourse constant;
      also fix the pre-existing copy-paste error in `config-schema.md`
      where `replay_window_seconds`'s comment incorrectly says it
      "Corresponds to env var DISCOURSE_WEBHOOK_SECRET"; verify
      `tests/unit/test_config.py` gains a case loading a config with
      `workflow_name` set and asserting it round-trips onto
      `ServiceConfig.discourse.webhook.workflow_name`.

## 2. Discourse trigger implementation

- [x] 2.1 Implement `src/triggers/discourse.py: matches(trigger, event)`
      for the `discourse_trust_level` trigger type: matches when
      `trigger.type == event.type == "discourse_trust_level"` and
      `event.payload["new_trust_level"] >= trigger.threshold` (per
      design.md — no crossing-only logic); verify
      `tests/unit/triggers/test_discourse.py` (new) covers: threshold met,
      threshold exceeded, and threshold not met.
- [x] 2.2 Add `build_trust_level_event(payload: dict, *, discourse_base_url:
      str) -> TriggerEvent` to `src/triggers/discourse.py`, constructing a
      `TriggerEvent(type="discourse_trust_level", openmrs_id=payload["username"],
      source=discourse_base_url, payload={"old_trust_level": ...,
      "new_trust_level": ...})` from an already-parsed, already-validated
      payload dict; verify the same test file covers it builds the
      expected `TriggerEvent`.
- [x] 2.3 Register `"discourse_trust_level"` in
      `src/triggers/__init__.py: register_all()`; verify
      `tests/unit/engine/test_evaluator.py::test_registries_are_populated_on_import`
      gains an assertion that `"discourse_trust_level" in
      evaluator.TRIGGER_MATCHERS`.

## 3. Webhook endpoint implementation

- [x] 3.1 Implement `src/api/webhooks.py: create_webhooks_router(*,
      webhook_secret, replay_window_seconds, workflow_name, audit_conn) ->
      APIRouter`, mirroring `create_slack_app()`'s factory+context shape
      (a `WebhookContext` dataclass, per design.md); the route reads the
      raw body first, verifies `X-Discourse-Workflow-Secret` via HMAC-SHA256
      with `hmac.compare_digest` (HTTP 403 on failure), then checks
      `X-Discourse-Workflow` against `workflow_name` (HTTP 400 on
      mismatch); verify `tests/unit/api/test_webhooks.py` (new directory)
      covers both rejection paths return the right status and that
      nothing downstream (JSON parsing, rule evaluation) is attempted
      when either check fails.
- [x] 3.2 Parse the JSON body and validate `username`, `new_trust_level`,
      and `timestamp` are present with the expected types (HTTP 400 on a
      missing/malformed field, without touching the rules engine); then
      check the parsed `timestamp` against `replay_window_seconds` using
      `datetime.fromisoformat()` (HTTP 400 if outside the window, past or
      future); verify the same test file covers: malformed JSON, a
      missing required field, a timestamp older than the window, and a
      timestamp further in the future than the window.
- [x] 3.3 On a request passing all checks, build the `TriggerEvent` via
      `build_trust_level_event()`, call `load_rules()` + `evaluate()` +
      `execute_rule()` for each matched rule (mirroring the Slack
      handlers), and respond HTTP 200 regardless of whether any rule
      matched; verify `tests/integration/test_discourse_trust_level_flow.py`
      (new, mirroring `test_slack_trust_flow.py`'s structure) exercises
      the full path with a mocked Keycloak client against the real
      `config/rules.example.yaml`, covering: a successful grant (status
      200, Keycloak group added, one audit row with `trigger_src` equal
      to the configured Discourse base URL), a no-op grant (user already
      has the groups), and no rule matching a `new_trust_level` below any
      configured threshold.

## 4. FastAPI wiring

- [x] 4.1 In `src/main.py`, replace `app.include_router(webhooks.router)`
      with a call to `webhooks.create_webhooks_router(...)`, resolving
      `webhook_secret` from `os.environ["DISCOURSE_WORKFLOW_SECRET"]`,
      `replay_window_seconds` from
      `os.environ.get("DISCOURSE_REPLAY_WINDOW_SECONDS",
      config.discourse.webhook.replay_window_seconds)`, `workflow_name`
      from `config.discourse.webhook.workflow_name`, and `audit_conn`
      from the already-constructed connection; verify
      `tests/unit/test_main.py` still passes (extend its dummy-env-var
      fixture and config YAML with `DISCOURSE_WORKFLOW_SECRET` and
      `workflow_name`) and `GET /health` still returns `200`.

## 5. Security-focused tests

- [x] 5.1 Add `tests/security/test_discourse_webhook.py`, mirroring the
      existing Slack security tests' structure: a request with an invalid
      `X-Discourse-Workflow-Secret` is rejected (403) before any Keycloak
      or audit call happens, and a validly-signed request with the wrong
      `X-Discourse-Workflow` value is rejected (400) before any
      downstream processing, per the `discourse-trust-level-trigger`
      spec's authorization requirements; verify the tests pass under
      `pytest`.

## 6. Docs

- [x] 6.1 Update `CLAUDE.md`'s "Current state" note to include the
      Discourse trust-level webhook trigger among the implemented pieces,
      and remove it from the list of what remains stubbed; verify by
      re-reading the file against the actual final behavior.

## 7. Full verification

- [x] 7.1 Run `pytest` and confirm every unit, integration, and security
      test — old and new — passes; run `python -m py_compile` over all
      changed files under `src/`.
