## Context

This is the first real implementation in the repo: everything under `src/`
is currently a stub (see `CLAUDE.md`). This change turns four stub clusters
into working code — `src/engine/*`, `src/triggers/slack.py`,
`src/actions/keycloak.py` + `src/integrations/keycloak.py`, and
`src/audit/db.py` — and adds the config-loading and FastAPI/Slack-Bolt
wiring needed to run them. See `proposal.md` - Why for motivation and the
four capability specs under `specs/` for the behavior contract. This
document covers the cross-module wiring the specs don't (and shouldn't)
pin down: event shape, dispatch mechanism, config loading, and how
Slack Bolt mounts into FastAPI.

## Goals / Non-Goals

**Goals:**
- Define the concrete shape of a "trigger event" flowing from an API layer
  into the rules engine, since three specs (`rules-engine`,
  `slack-trust-command`, `keycloak-access-provisioning`) all depend on it.
- Define how trigger/action `type` strings map to handler functions so the
  engine core needs no changes to add a type (per the `rules-engine` spec).
- Define where and how `config.yaml` is loaded once at startup and handed to
  the pieces that need it (Keycloak client, Slack app, rules/audit paths).
- Define how the Slack Bolt app is mounted into the existing FastAPI app.

**Non-Goals:**
- Discourse webhook trigger, `/revoke`, `/trust-status`, rate limiting,
  admin log-level API, dry-run mode — separate future changes.
- Anything about *what* the system must do externally — that's fixed by the
  specs in this change; this document is implementation approach only.

## Decisions

### Trigger event shape: a single generic envelope
Add `TriggerEvent` to `src/engine/models.py`:
```python
class TriggerEvent(BaseModel):
    type: str                    # e.g. "slack_trust_command"
    openmrs_id: str              # target user
    source: str | None = None    # e.g. issuing Slack username
    payload: dict[str, Any] = {}
```
`src/api` handlers (or `src/integrations/slack.py`) construct this after
their own authorization checks pass; `src/engine/evaluator.py` never sees
raw Slack/Discourse payloads. Alternative considered: a separate event
class per trigger type (e.g. `SlackTrustEvent`, `DiscourseTrustEvent`).
Rejected for now — it would need a union type in the evaluator and buys
nothing until a second trigger type (Discourse) actually lands with
different fields; revisit then if `payload` gets unwieldy.

### Dispatch: type-keyed registries, populated by import
`src/engine/evaluator.py` holds two module-level dicts:
```python
TRIGGER_MATCHERS: dict[str, Callable[[Trigger, TriggerEvent], bool]]
ACTION_EXECUTORS: dict[str, Callable[[Action, TriggerEvent], ActionResult]]
```
populated at import time by `src/triggers/__init__.py` and
`src/actions/__init__.py` importing their concrete modules and registering
functions under the same `type` strings used in `rules.yaml` (e.g.
`"slack_trust_command"`, `"keycloak_add_groups"`). Evaluating a rule becomes
a dict lookup by `trigger.type` / `action.type`, satisfying the
`rules-engine` spec's "no core changes for a new type" requirement.
Alternative considered: `importlib`-based plugin discovery scanning
`src/triggers/` and `src/actions/` directories. Rejected — unnecessary
indirection for four known modules; explicit registration is easier to read
and to unit test in isolation.

### Action executors return a structured result, not raw values
Change the stub signatures in `src/actions/keycloak.py` from returning `Any`
to returning:
```python
class ActionResult(BaseModel):
    status: Literal["success", "no_change", "failure"]
    detail: str | None = None
    action_detail: str | None = None   # e.g. JSON list of groups actually added
```
`evaluator.execute_rule()` always gets a structured result to hand to
`src/audit/db.record_event()` — no separate exception-vs-return-value
branching for the expected outcomes (no-op, not-found, unreachable) that
the `keycloak-access-provisioning` spec requires. An executor still may
raise for genuinely unexpected errors (e.g. a bug), which
`execute_rule()` catches once and records as `status="failure"` with the
exception message, so a programming error can't crash the whole event
evaluation.

### Config loading: new `src/config.py`, loaded once at startup
Add `src/config.py` with a `ServiceConfig` Pydantic model mirroring
`config.yaml`'s shape (`discourse`, `keycloak`, `slack`, `rate_limiting`,
`logging`, `database`, `admin` sections) and a `load_config(path) ->
ServiceConfig` function. `src/main.py` calls this once at startup (module
import time, matching "loaded once, restart to change" semantics) and
constructs the Keycloak client, Slack Bolt app, and audit DB connection
from it, storing them on `app.state` for the route handlers to use.
Secrets (`KEYCLOAK_CLIENT_SECRET`, `SLACK_BOT_TOKEN`, etc.) are read
directly from `os.environ` in this same startup path, never through the
YAML model — consistent with `config.yaml` only documenting env var names.
This file wasn't in the original repo-plan tree; it's a natural home given
`config.yaml` parsing didn't fit any existing module.

### Config/rules file paths: env-var overridable, container defaults
Default `CONFIG_PATH=/config/config.yaml` and `RULES_PATH=/config/rules.yaml`
(matching the production host-mount layout in the spec), overridable via
new optional `CONFIG_PATH` / `RULES_PATH` env vars. This lets local
non-Docker development point at `./config/config.yaml` (as the README's
setup steps already produce) via `.env`, while `docker-compose.yml`'s
`./config:/config` mount means the container defaults just work without
overrides. `.env.example` gains these two optional entries.

### Mounting Slack Bolt into FastAPI
Use `slack_bolt.adapter.fastapi.SlackRequestHandler`, mounted as a route in
`src/main.py` (e.g. `POST /slack/commands`) that delegates to a
`slack_bolt.App` built in `src/integrations/slack.py`. Slack Bolt's `App`
performs signature verification internally when constructed with
`signing_secret`, so `src/triggers/slack.py` does not hand-roll HMAC
verification — it only implements the channel-restriction and
event-construction logic once Bolt has already validated the request.
Alternative considered: verify signatures by hand against the raw request
body. Rejected — Bolt's implementation is the maintained, tested one; no
reason to duplicate it.

### "Silent rejection" means no visible Slack message, not no HTTP response
The `slack-trust-command` spec's "no response" (for wrong-channel commands)
is implemented as: still send Slack the empty/ack HTTP response it requires
to close out the slash-command request (otherwise Slack shows the user an
"operation timed out" error, which is itself an information leak), but post
no visible confirmation/error message and take no rule-engine action. This
doesn't change externally observable behavior described in the spec — the
channel never sees a response — so it doesn't need a spec update, just a
clear implementation note here.

## Risks / Trade-offs

- **[Risk]** A bug in a specific action executor raising instead of
  returning an `ActionResult` could still crash event evaluation for other
  matched rules in the same event. → **Mitigation:** `execute_rule()` wraps
  each action execution in a single try/except and records a `failure` audit
  row, so one rule's bug doesn't block other matched rules in the same
  batch.
- **[Risk]** `TriggerEvent.payload` as a loose `dict` sidesteps strong typing
  per trigger type, which could let a malformed payload reach a matcher
  function. → **Mitigation:** authorization/parsing happens in the
  `src/triggers/slack.py` module before a `TriggerEvent` is ever
  constructed (per spec: signature + channel checks first), so by the time
  the evaluator sees an event, it's already been validated at the source.
- **[Risk]** Introducing `src/config.py`, not in the original repo plan,
  is a structural deviation. → **Mitigation:** it's additive (no existing
  file moves), and `CLAUDE.md`'s Layout section will need a one-line
  addition once this lands — noted in tasks.md.

## Migration Plan

No live deployment exists yet, so there's no rollback/migration concern for
this change — it's the first working code. Local dev picks it up via
`docker compose up --build` or `uvicorn src.main:app --reload` per the
README, with `config.yaml`/`rules.yaml` copied from the `.example` files.
