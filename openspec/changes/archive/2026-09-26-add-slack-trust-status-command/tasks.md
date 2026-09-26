# Tasks

## 1. Discourse integration

- [x] 1.1 Implement `src/integrations/discourse.py: DiscourseClient`
      wrapping `pydiscourse.DiscourseClient`, with `get_trust_level(openmrs_id)`
      calling `.user(openmrs_id)["trust_level"]`, no retry (per design.md);
      add the same `build_client()` / `set_client()` / `get_client()`
      module-level singleton functions `src/integrations/keycloak.py` has;
      verify `tests/unit/integrations/test_discourse.py` (new) covers a
      successful lookup returning an int and a failure (mocked
      `DiscourseClientError` and a mocked connection error) propagating
      unchanged (no retry/swallowing at this layer).

## 2. Audit read function

- [x] 2.1 Implement `src/audit/db.py: get_recent_events(conn, openmrs_id,
      *, limit=5)` returning the most recent matching rows ordered newest
      first; verify `tests/unit/audit/test_db.py` gains a case that
      inserts several rows for different `openmrs_id`s, calls
      `get_recent_events()` for one of them with `limit=2`, and asserts
      only that user's 2 most recent rows come back in newest-first
      order.

## 3. Slack /trust-status command

- [x] 3.1 In `src/integrations/slack.py`, register a `/trust-status`
      command listener on the existing `App` (alongside `/trust` and
      `/revoke`) and add `_handle_trust_status()`: inline channel-id
      check (no `TriggerEvent`, per design.md — silent return on
      mismatch), usage message on empty `openmrs_id`, then look up
      Keycloak groups via `keycloak_integration.get_client().get_user_groups()`;
      verify `tests/unit/integrations/test_slack.py` gains a case
      confirming the returned `App` has a registered `/trust-status`
      command listener (mirroring the existing `/trust`/`/revoke`
      assertions).
- [x] 3.2 Implement the unknown-user short-circuit: on
      `UserNotFoundError` from the Keycloak lookup, respond immediately
      with a "not found" message and skip the Discourse/audit lookups
      (per design.md); verify a unit test in
      `tests/integration/test_slack_trust_status_flow.py` (new, see 3.4)
      covers this path.
- [x] 3.3 Implement the Discourse trust-level and audit-history lookups
      as independent try/except blocks (per design.md's partial-data
      decision): a Keycloak connectivity failure, a Discourse failure, or
      an audit-read failure each mark only their own section
      "unavailable" in the response without preventing the other two
      sections from being reported; format the combined response
      (OpenMRS ID, Keycloak groups or unavailable note, Discourse trust
      level or unavailable note, last 5 audit entries or unavailable
      note); verify the same integration test file covers: full success,
      Discourse-unavailable-but-Keycloak/audit-ok, and
      Keycloak-connectivity-failure-but-Discourse/audit-ok.
- [x] 3.4 Create `tests/integration/test_slack_trust_status_flow.py`
      (mirroring `test_slack_trust_flow.py`'s structure) exercising
      `_handle_trust_status()` directly with mocked Keycloak and
      Discourse clients and a real temp audit DB seeded with a few rows,
      covering every scenario in tasks 3.2 and 3.3, plus: confirm no
      `audit_log` row is written as a side effect of running
      `/trust-status` itself (per design.md — status checks aren't
      access-provisioning actions).

## 4. Security-focused tests

- [x] 4.1 Add `tests/security/test_slack_trust_status_command.py`,
      mirroring `test_slack_trust_command.py`: a request with an invalid
      Slack signature is rejected before any Keycloak/Discourse/audit
      call happens, and a validly-signed request from an unauthorized
      channel results in no lookups and no visible Slack response, per
      the `slack-trust-status-command` spec's authorization
      requirements; verify the tests pass under `pytest`.

## 5. FastAPI/startup wiring

- [x] 5.1 In `src/main.py`, construct and install the `DiscourseClient`
      singleton at startup (mirroring the existing Keycloak client
      wiring), using `config.discourse.base_url` and
      `DISCOURSE_API_KEY`/`DISCOURSE_API_USERNAME`; verify
      `tests/unit/test_main.py` still passes (extend its dummy-env-var
      fixture with the two new Discourse env vars) and confirms
      `GET /health` still returns `200`.

## 6. Docs

- [x] 6.1 Update `CLAUDE.md`'s "Current state" note to include
      `/trust-status` among the implemented commands; verify by
      re-reading the file against the actual final behavior.

## 7. Full verification

- [x] 7.1 Run `pytest` and confirm every unit, integration, and security
      test — old and new — passes; run `python -m py_compile` over all
      changed files under `src/`.
