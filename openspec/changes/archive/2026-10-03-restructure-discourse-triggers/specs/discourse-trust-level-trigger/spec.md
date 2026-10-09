# Spec Delta

## REMOVED Requirements

### Requirement: Webhook signature is verified before any other processing
**Reason**: Superseded by `discourse-workflow-trigger`'s equivalent
requirement, which verifies the same `X-Discourse-Workflow-Signature` header
but is no longer scoped to a single hardcoded workflow name.
**Migration**: No action needed — the signature scheme and secret
(`DISCOURSE_WORKFLOW_SECRET`) are unchanged. The existing Discourse
Workflow's HTTP action step requires no reconfiguration.

### Requirement: Requests are restricted to the configured workflow
**Reason**: The single configured workflow name
(`config.yaml`'s `discourse.webhook.workflow_name`) is replaced by
`discourse-workflow-trigger`'s per-rule `type: workflow, name: <name>`
matching — any workflow name a rule references is now accepted, not
just one hardcoded value.
**Migration**: Remove `discourse.webhook.workflow_name` from
`config.yaml`. Add a rule trigger `{type: workflow, name: "trusted"}`
(or whatever the Workflow's actual name is) to `rules.yaml` in its
place.

### Requirement: Stale requests are rejected as potential replays
**Reason**: Deliberately removed, not replaced. Every action this
service takes is idempotent (`keycloak_add_groups`/
`keycloak_remove_groups`), so re-processing a replayed or duplicate
event is harmless; neither native webhooks nor Workflow payloads are
expected to carry a timestamp field worth checking.
**Migration**: Remove `discourse.webhook.replay_window_seconds` from
`config.yaml` and `DISCOURSE_REPLAY_WINDOW_SECONDS` from the
environment. No functional replacement.

### Requirement: A valid request triggers rule evaluation
**Reason**: Superseded by `discourse-workflow-trigger`'s and
`discourse-webhook-trigger`'s equivalent requirements, generalized from
the single `discourse_trust_level` trigger type to `type: workflow`/
`type: webhook` matched by name.
**Migration**: Replace any `discourse_trust_level` trigger in
`rules.yaml` with the corresponding `type: workflow` or `type: webhook`
trigger.

### Requirement: Trigger matches at or above the configured threshold
**Reason**: Deliberately removed, not replaced. The `threshold` check
existed because the Discourse Workflow fired on every trust-level
change, not just the crossing into the target level; filtering on
payload content is out of scope for this MVP (deferred to a future
`condition`-style enhancement) and isn't needed today because every
configured trigger source already fires only for the event this
service should act on.
**Migration**: Remove the `threshold` field from any
`discourse_trust_level` trigger when migrating it to `type: workflow`/
`type: webhook`. If payload-content filtering is genuinely needed for a
future trigger source, that is a new, separate enhancement.

### Requirement: The service acknowledges the request's outcome
**Reason**: Superseded by `discourse-webhook-trigger`'s and
`discourse-workflow-trigger`'s equivalent requirements, which cover the
same HTTP status codes for the generalized mechanism-branching
endpoint.
**Migration**: No action needed — `POST /webhook/discourse` keeps
responding HTTP 200 for an accepted/processed request and HTTP 4xx for
a rejected one.
