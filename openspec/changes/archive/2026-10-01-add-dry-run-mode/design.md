# Design

## Context

`src/engine/evaluator.py: execute_rule()` dispatches each matched rule's
actions to `ACTION_EXECUTORS[action.type]` (currently `keycloak_add_groups`
→ `src/actions/keycloak.py: add_groups`, `keycloak_remove_groups` →
`remove_groups`), then writes one audit row per action via
`record_event()`. Those action functions call
`src/integrations/keycloak.py: KeycloakClient.add_user_to_groups` /
`remove_user_from_groups`, which already read current group membership
live before deciding what (if anything) to mutate — the idempotency check
every action already needs. Two entry points construct a `TriggerEvent`
and call `evaluate()` + `execute_rule()`: `src/api/webhooks.py`'s
`discourse_webhook` route, and `src/integrations/slack.py`'s
`_handle_trust`/`_handle_revoke`. See proposal.md for why dry-run mode is
needed and how it's toggled (`config.yaml`'s `dry_run`, overridable by
`DRY_RUN`).

## Goals / Non-Goals

**Goals:**
- Thread a single `dry_run: bool` from startup config through both entry
  points into `execute_rule()` and the two Keycloak actions, with no
  action executor needing to know *why* it's in dry-run mode — just that
  it is.
- Keep the engine itself unaware of what "dry-run" means for any
  particular action type — it only carries the flag, matching the
  existing "engine dispatches generically by type" design.
- Make a dry-run audit row and a dry-run Slack response unmistakable, so
  no one confuses a simulation with a real grant/revoke.

**Non-Goals:**
- No per-rule or per-request dry-run override — this proposal's "one
  process-wide setting" scenario is deliberate (see proposal.md's
  AskUserQuestion exchange); a future change could add finer granularity
  if ever needed.
- No change to `/trust-status` — it already never reaches the rules
  engine or touches `ACTION_EXECUTORS`.
- No change to the Discourse webhook's HTTP response contract — it
  already returns `{"status": "ok"}` / HTTP 200 regardless of whether
  any rule matched or what the outcome was; dry-run doesn't change that,
  only what's in the audit log.

## Decisions

### `dry_run: bool` threads through `execute_rule()` and every executor
`ACTION_EXECUTORS` entries change signature from
`Callable[[Action, TriggerEvent], ActionResult]` to
`Callable[[Action, TriggerEvent, bool], ActionResult]` (positional
`dry_run`, defaulting to `False` isn't needed since `execute_rule()`
always passes it explicitly). `execute_rule(rule, event, *, conn,
dry_run: bool = False)` passes `dry_run` to `executor(action, event,
dry_run)`. Alternative considered: a dry-run-aware wrapper around
`ACTION_EXECUTORS` that short-circuits before calling the real executor,
using a generic "would-be" result. Rejected — the engine would then need
to synthesize a plausible `ActionResult` for an action type it knows
nothing about (the groups it would add is Keycloak-specific knowledge);
threading the flag down to the one place that *does* know (the Keycloak
action/client) is simpler and keeps the engine generic.

### `KeycloakClient` computes the diff but skips the mutating call
`add_user_to_groups`/`remove_user_from_groups` gain a `dry_run: bool =
False` keyword parameter. The existing logic already separates "read
current membership live" from "call `group_user_add`/`group_user_remove`
per group not yet in that membership" — dry-run simply skips the
mutating call inside that loop, still returning the same list of group
names it *would* have added/removed. `src/actions/keycloak.py:
add_groups`/`remove_groups` pass `dry_run` straight through and build
their `ActionResult` exactly as today except `status="dry_run"` instead
of `"success"`/`"no_change"` (the "would add" vs. "would be a no-op"
distinction stays in `detail`/`action_detail`, not `status` — see the
`audit-log` delta: `status` only grows one new value, not a cross
product of dry-run × outcome).

### `ActionResult.status` gains a fourth literal: `"dry_run"`
`src/engine/models.py: ActionResult.status: Literal["success", "no_change",
"failure", "dry_run"]`. Chosen over a separate `ActionResult.dry_run: bool`
field — a single status value is simpler for every consumer (audit log,
Slack formatters) to branch on, and `status="dry_run"` by itself already
answers "was this real?" without inspecting a second field. The `detail`
string is where "would add X" vs. "would already have X" lives, matching
how `no_change` vs. `success` already differ only in `detail` today, not
in some third dimension.

### Slack response formatters get a dry-run branch, checked first
`_format_response`/`_format_revoke_response` (`src/integrations/slack.py`)
gain a branch checking `all(o.status == "dry_run" for o in outcomes)`
before the existing failure/no-change/success checks (an action either
runs in dry-run or it doesn't, uniformly across all outcomes for one
event, since `dry_run` is one process-wide flag passed to every action
of a single `execute_rule()` call). Wording distinguishes "would be
granted" vs. "already trusted" using the same `detail` text the action
already produced, prefixed with a clear dry-run disclosure, e.g.
`` `foobar` would be granted community edit access (dry-run — no change
made). `` Alternative considered: a generic `"[DRY RUN] " +
existing_message` prefix applied uniformly. Rejected — the existing
messages use past tense ("has been granted"), which reads as having
already happened; a dry-run message needs its own wording, not a prefix
glued onto language that asserts the opposite of what's true.

### `main.py` wiring mirrors `DISCOURSE_REPLAY_WINDOW_SECONDS`
```python
_dry_run_override = os.environ.get("DRY_RUN", "").strip().lower()
dry_run = (
    _dry_run_override in ("true", "1", "yes", "on")
    if _dry_run_override
    else config.dry_run
)
```
passed into both `webhooks.create_webhooks_router(..., dry_run=dry_run)`
and `create_slack_app(..., dry_run=dry_run)`, each storing it on their
existing context dataclass (`WebhookContext.dry_run`,
`SlackContext.dry_run`) and passing it to every `execute_rule(...,
dry_run=context.dry_run)` call site.

## Risks / Trade-offs

- **[Risk]** An operator enables dry-run in `config.yaml` for testing and
  forgets to disable it, silently making the service a no-op in
  production. → **Mitigation:** `dry_run` defaults to `false`; the Slack
  response and (per the `dry-run-mode` spec) every audit row are
  unmistakable while it's active, so this would surface quickly on the
  very first real `/trust` attempt rather than failing silently.
- **[Risk]** `DRY_RUN` boolean parsing (`"true"/"1"/"yes"/"on"` vs.
  anything else) could surprise someone expecting Python's `bool("false")
  == True` footgun. → **Mitigation:** explicit allow-list for "true",
  anything else (including blank, handled separately) is `false` — safer
  default than accidentally enabling it.

## Migration Plan

Purely additive — `dry_run` defaults to `false`/off, so existing
deployments behave identically until someone opts in. No audit log
migration needed: `status` is an unconstrained `TEXT` column already (no
`CHECK` constraint), so the new `"dry_run"` value needs no schema change.
