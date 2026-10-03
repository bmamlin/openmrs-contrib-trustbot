# OpenMRS Trust Bot — Project Spec

> **Status:** Draft / In Progress  
> **Last updated:** 2026-09-08

---

## 1. Problem Statement

The OpenMRS community currently grants trust levels and service access (JIRA, Confluence, etc.) through **manual, human-driven processes**. A community member requesting JIRA/Confluence access requires an ITSM member to:

1. Log into the Keycloak admin console
2. Find the user by OpenMRS ID
3. Manually add the user to the appropriate Keycloak groups (e.g. `jira-users`, `jira-trunk-developer`, `confluence-users`)

This process is time-consuming, dependent on ITSM volunteer availability, and creates unnecessary friction for legitimate new contributors. The goal is to **automate and simplify the elevation of trust and privileges** for community members based on objective signals of community participation.

---

## 2. Goals

- Reduce ITSM volunteer time spent on routine trust/access grants
- Automatically detect when community members reach trust thresholds (via Discourse activity)
- Allow trusted community members to vouch for others via Slack commands
- Automatically provision appropriate access in downstream systems (Keycloak → JIRA, Confluence, etc.) when trust thresholds are met

---

## 3. Architecture Overview

The **OpenMRS Trust Bot** is deployed as a **Docker container** within the existing OpenMRS OpenStack infrastructure, managed via the existing Terraform + Docker Compose infrastructure-as-code pipeline.

> **Identity linking:** Discourse users authenticate via Keycloak SSO. The Discourse username is always identical to the OpenMRS ID / Keycloak username — this is the reliable, canonical key for cross-system identity lookups. No fuzzy matching or email fallback is needed.

### 3.1 Key Integrations

| System | Role | Integration Type |
|---|---|---|
| **Discourse** (talk.openmrs.org) | Source of trust level signals | Discourse webhooks |
| **Keycloak** (id-new.openmrs.org) | Identity & group management; SSO source of truth | Keycloak Admin REST API |
| **Slack** | Human-in-the-loop trust commands | Slack Bolt / slash commands |
| **JIRA** | Issue tracker; access gated by Keycloak group | Via Keycloak group (`jira-users`, `jira-trunk-developer`) |
| **Confluence** | Wiki; access gated by Keycloak group | Via Keycloak group (`confluence-users`) |

### 3.2 Trust Signal Sources

- **Discourse Trust Levels** — Discourse natively calculates trust levels (0–4) based on reading, posting, and engagement activity. The service monitors for users reaching a configurable threshold level via webhooks.
- **Slack commands** — A trusted community member can issue `/trust <openmrs-id>` or `/revoke <openmrs-id>` from the designated private Slack channel.

### 3.3 Host-Mounted Volumes

Two directories are mounted from the Docker host into the container:

| Host path (example) | Container path | Purpose |
|---|---|---|
| `/opt/trustbot/config/` | `/config/` | YAML rules files; changes are observed immediately without restart |
| `/opt/trustbot/data/` | `/data/` | SQLite audit database (`audit.db`); persisted across container restarts |

Mounting config and data from the host simplifies backups, allows config edits without rebuilding the image, and keeps persistent state outside the container lifecycle.

---

## 4. Core Design: Rules Engine (IFTTT Model)

The service is built around a simple, declarative **rules engine**: a collection of rules, each mapping one or more **triggers/criteria** to one or more **actions**. The engine itself is generic; all community-specific logic lives in YAML configuration files, not code.

```yaml
rules:
  - name: "Grant community edit access at Discourse TL2"
    triggers:
      - type: workflow            # a Discourse Workflow's HTTP action
        name: "trusted"           # matched against X-Discourse-Workflow
    actions:
      - type: keycloak_add_groups
        groups: [jira-users, jira-trunk-developer, confluence-users]

  - name: "Grant community edit access (manual)"
    triggers:
      - type: slack_trust_command
        channel: "C0123456789"   # designated private channel ID
    actions:
      - type: keycloak_add_groups
        groups: [jira-users, jira-trunk-developer, confluence-users]

  - name: "Revoke community edit access"
    triggers:
      - type: slack_revoke_command
        channel: "C0123456789"
    actions:
      - type: keycloak_remove_groups
        groups: [jira-users, jira-trunk-developer, confluence-users]
```

YAML files are loaded from the mounted `/config/` directory. See the [YAML Configuration Schema](openmrs-trustbot-config-schema.md) document for full schema details and annotated examples.

- **`rules.yaml`** — re-read on every trigger event; rule changes take effect immediately without restarting the service
- **`config.yaml`** — loaded once at startup; changes to service-level settings require a container restart

### 4.1 Triggers (known and anticipated)

| Trigger Type | Description | Status |
|---|---|---|
| `workflow` | A named Discourse Workflow's HTTP action fires (matched by `name`, e.g. `"trusted"`) | **In scope (MVP)** |
| `webhook` | A named native Discourse webhook event fires (matched by `name`, e.g. `"user_promoted"`) | **In scope (MVP)** |
| `slack_trust_command` | Trusted member issues `/trust <openmrs-id>` in designated Slack channel | **In scope (MVP)** |
| `slack_revoke_command` | Trusted member issues `/revoke <openmrs-id>` in designated Slack channel | **In scope (MVP)** |
| `github_contribution` | User meets a contribution threshold in a GitHub org/repo | Future |
| `jira_contribution` | User meets a threshold of JIRA activity | Future |
| `confluence_contribution` | User meets a threshold of Confluence edits | Future |

> **Note:** `/trust-status <openmrs-id>` is a read-only query command, not a trigger — it does not go through the rules engine.

### 4.2 Actions (known and anticipated)

| Action Type | Description | Status |
|---|---|---|
| `keycloak_add_groups` | Add user to one or more Keycloak groups (grants JIRA, Confluence, etc.) | **In scope (MVP)** |
| `keycloak_remove_groups` | Remove user from one or more Keycloak groups (revoke access) | **In scope (MVP)** |
| `discourse_grant_badge` | Grant a badge to the user on Discourse | Future |
| `discourse_add_group` | Add user to a Discourse group | Future |
| `discourse_notify` | Send a Discourse message to the user | Future |
| `email` | Send an email notification to the user | Future |
| `slack_notify` | Send a Slack notification (to user or a channel) | Future |
| `github_grant_access` | Grant access to a GitHub repository or team | Future |

### 4.3 MVP Rule Set

| Rule | Trigger | Actions |
|---|---|---|
| Community edit access (automatic) | Discourse trust level ≥ 2 | Add to `jira-users`, `jira-trunk-developer`, `confluence-users` in Keycloak |
| Community edit access (manual) | `slack_trust_command` from designated private channel | Add to `jira-users`, `jira-trunk-developer`, `confluence-users` in Keycloak |
| Revoke community edit access | `slack_revoke_command` from designated private channel | Remove from `jira-users`, `jira-trunk-developer`, `confluence-users` in Keycloak |

All rule executions record the trigger source (automatic vs. manual, and the Slack username if manual) in the audit log. `/trust-status` is read-only and does not go through the rules engine.

### 4.4 No-Op Behavior

If a rule fires but produces no change (e.g. `/trust` is issued for a user who already has all the relevant Keycloak groups), the service:
- Records the event in the audit log, noting the intended action and that no change was made
- Returns a clear response to the caller (e.g. in Slack: "`foobar` is already trusted.")

---

## 5. Functional Requirements

### 5.1 Rules Engine

- [ ] Rules defined in `rules.yaml` in the mounted `/config/` directory; service config in `config.yaml`
- [ ] `rules.yaml` re-read on each trigger event so rule changes take effect immediately without restarting
- [ ] `config.yaml` loaded once at startup; service-level config changes require a container restart
- [ ] Each rule specifies: one or more triggers, logical combination (AND/OR, TBD), and one or more actions
- [ ] Engine evaluates all rules on each trigger event and executes all matching rules' actions
- [ ] All actions must be **idempotent** — safe to execute multiple times with the same result
- [ ] If an action produces no change, the audit log records the intended action and notes that no change was made
- [ ] Engine must be extensible: adding a new trigger type or action type requires no changes to core engine logic

### 5.2 Discourse Monitoring

- [ ] Expose a FastAPI POST endpoint to receive both native Discourse
      webhook events and Discourse Workflow HTTP action payloads
- [ ] Verify each request's signature on every incoming request before
      any processing (`X-Discourse-Event-Signature` for native
      webhooks, `X-Discourse-Workflow-Secret` for Workflows); reject
      unsigned or invalid requests with HTTP 403
- [ ] Route to a rule by the event/workflow's `name` (from
      `X-Discourse-Event` or `X-Discourse-Workflow`), declared in
      `rules.yaml` as `type: webhook`/`type: workflow` triggers — not a
      single hardcoded name in service config. An event/workflow name
      no rule references is acknowledged (HTTP 200) and ignored, not
      an error.
      Deliberately **not implemented**: replay-window/staleness
      rejection. Removed by design (see
      `openspec/changes/archive/*-restructure-discourse-triggers/design.md`)
      — every action this service takes is idempotent, so re-processing
      a replayed request is harmless; this is a considered trade-off,
      not an oversight.
- [ ] Username from the resolved payload is used directly as the
      OpenMRS ID / Keycloak username

### 5.3 Slack Integration

- [ ] Register the following slash commands in the OpenMRS Slack workspace, all restricted to the designated private channel:
  - `/trust <openmrs-id>` — grant community edit access
  - `/revoke <openmrs-id>` — revoke community edit access
  - `/trust-status <openmrs-id>` — display current trust state (see §5.3.1)
- [ ] Validate the source channel ID matches the configured designated private channel; reject commands from any other channel with no action taken
- [ ] Trigger rule evaluation as a `slack_trust_command` or `slack_revoke_command` event for the target OpenMRS ID
- [ ] Respond in Slack with a clear confirmation or descriptive error message for every command
- [ ] If a command produces no change, respond with a specific message (e.g. "`foobar` is already trusted.")
- [ ] Log all commands with Slack username of issuer, target OpenMRS ID, timestamp, and outcome

#### 5.3.1 `/trust-status` Response

The `/trust-status <openmrs-id>` command returns a formatted Slack response containing:
- OpenMRS ID
- Current Keycloak group memberships (relevant groups only, e.g. `jira-users`, `confluence-users`)
- Current Discourse trust level
- Summary of recent audit log entries for that user (e.g. last 5 events: action, trigger, timestamp, outcome)

This command is read-only and does not trigger rule evaluation.

### 5.4 Keycloak Integration

- [ ] Use Keycloak Admin REST API with a dedicated, least-privilege service account
- [ ] `keycloak_add_groups`: add user to specified groups; no-op (with audit note) if already a member
- [ ] `keycloak_remove_groups`: remove user from specified groups; no-op (with audit note) if not a member
- [ ] Always query Keycloak live for current group membership — do not cache or persist access state locally
- [ ] If the target OpenMRS ID does not exist in Keycloak, log an error and return a descriptive failure response
- [ ] If Keycloak is unreachable, retry once after a brief delay; if still unreachable, return an error (e.g. "Unable to reach Keycloak. Please try again later.") and log the failure

### 5.5 Audit & Logging

#### Audit Log (SQLite)

- [ ] All rule evaluations that result in an attempted action must produce an audit record in a SQLite database at `/data/audit.db`
- [ ] Audit database persisted via host-mounted Docker volume (not ephemeral container storage)
- [ ] Audit records are append-only; the service never updates or deletes records
- [ ] Schema:

```sql
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,          -- ISO 8601 UTC
    openmrs_id  TEXT    NOT NULL,          -- target user
    trigger     TEXT    NOT NULL,          -- e.g. 'workflow', 'webhook', 'slack_trust_command'
    trigger_src TEXT,                      -- e.g. Slack username, Discourse webhook URL
    rule_name   TEXT    NOT NULL,          -- matched rule name from YAML
    action      TEXT    NOT NULL,          -- e.g. 'keycloak_add_groups'
    action_detail TEXT,                    -- e.g. JSON list of groups
    status      TEXT    NOT NULL,          -- 'success' | 'no_change' | 'failure'
    detail      TEXT                       -- error message or 'no change: already a member' etc.
);
```

#### Application Logging

- [ ] Application log level configurable via `LOG_LEVEL` environment variable (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- [ ] Log level changeable at runtime without restarting the service via a protected admin API endpoint
- [ ] Logs emitted to stdout/stderr in structured JSON format for compatibility with Docker logging infrastructure
- [ ] DEBUG mode must never log secrets, credentials, or raw webhook payloads containing sensitive data

#### Future: Admin UI (post-MVP)

- Expose audit log viewing through a simple, authorization-protected web interface
- Expose log level control (INFO ↔ DEBUG) through the same interface
- FastAPI provides the HTTP foundation; no additional infrastructure required

---

## 6. Security Requirements

Security is a primary concern given the service directly controls privilege escalation. A successful attack or misconfiguration could allow a user to inappropriately elevate their own or others' community access.

### 6.1 Authorization

- [ ] Slack `/trust` and `/revoke` commands must verify the source channel ID matches the designated private channel before taking any action; commands from any other channel are rejected silently (no action, no response)
- [ ] The Keycloak service account must be **least-privilege**: scoped only to add/remove users from the specific groups managed by this service
- [ ] Slack command endpoints must verify the Slack request signature (using the Slack signing secret) to prevent spoofed requests

> **Self-elevation:** Because Slack usernames are not guaranteed to match OpenMRS IDs, reliably detecting self-elevation via Slack commands is deferred. The private channel membership model (only vetted `/dev/5` members are admitted) is the primary control. A future enhancement could add a Slack username → OpenMRS ID mapping to enable explicit self-elevation checks.

### 6.2 Secrets Management

- [ ] All credentials (Keycloak service account, Slack signing secret, Discourse webhook secret, Discourse API key) stored as environment variables injected at runtime; never committed to source control
- [ ] Secrets must not appear in application logs at any log level

### 6.3 Input Validation

- [ ] All external inputs (Slack payloads, Discourse webhook/Workflow payloads) validated and sanitized before processing
- [ ] OpenMRS IDs received from external sources validated to exist in Keycloak before any action is taken
- [ ] ~~Webhook replay protection~~ **Deliberately not implemented**: every action this service takes is idempotent, so re-processing a replayed or duplicate Discourse request is harmless. Signature verification (above) remains the actual authentication control.

### 6.4 Rate Limiting

- [ ] The Discourse webhook endpoint must enforce rate limiting to prevent abuse from a misconfigured or compromised Discourse instance
- [ ] Slack command endpoints must enforce per-user rate limiting to prevent a channel member from issuing commands in rapid succession
- [ ] Rate limit thresholds configurable via environment variables
- [ ] Requests exceeding rate limits receive an HTTP 429 response (webhook) or a Slack error message; all rate limit violations are logged

### 6.5 Testing & Verification

- [ ] Unit tests for all trigger parsers, rule evaluation logic, and action executors
- [ ] Integration tests covering the end-to-end rule evaluation pipeline
- [ ] Specific security-focused tests for: unauthorized Slack channel, malformed payloads, invalid Discourse webhook/Workflow signatures, rate limit enforcement, requests for non-existent OpenMRS IDs
- [ ] A **dry-run / simulation mode** in which all rule actions are evaluated and logged but no changes are made to external systems (Keycloak, etc.)

### 6.6 Observability

- [ ] Health check endpoint (`GET /health`) for Docker/monitoring integration
- [ ] Authorization failures and rate limit violations logged at WARNING level or above
- [ ] All Keycloak failures logged with enough detail to diagnose the problem

---

## 7. Non-Functional Requirements

- **Deployment:** Docker container; managed via existing Terraform + Docker Compose IaC
- **Language:** Python 3.12+
- **Key libraries:** FastAPI, slack-bolt, python-keycloak, pydiscourse, PyYAML/strictyaml, pytest
- **Idempotency:** All provisioning actions must be safe to retry without side effects
- **Simplicity:** Core engine should be small and easy to understand; complexity lives in config, not code
- **Extensibility:** New trigger types and action types should be addable without modifying existing engine logic
- **Uptime:** Near-100%; Docker restart policy should be set to `always` or `unless-stopped`

---

## 8. Open Questions

1. ~~**Trust level mapping**~~ **Resolved:** Discourse Trust Level ≥ 2 triggers the grant of `jira-users`, `jira-trunk-developer`, and `confluence-users` Keycloak groups. This is the primary MVP rule.
2. ~~**User identity linking**~~ **Resolved:** Users authenticate to Discourse via Keycloak SSO, so the Discourse username is always identical to the OpenMRS ID / Keycloak username. Keycloak is the authoritative source for email addresses.
3. ~~**Who is "trusted" in Slack?**~~ **Resolved:** Authorized users are members of the Discourse `/dev/5` group. MVP uses a restricted private Slack channel whose membership is limited to `/dev/5` members (managed by ITSM). The service validates the source channel ID against a configured value. A Slack username → OpenMRS ID mapping may be added in future to enable explicit self-elevation checks.
4. ~~**`/trust` command behavior**~~ **Resolved:** `/trust <openmrs-id>` grants basic "member of the community" access via a `slack_trust_command` rule — same Keycloak groups as the Discourse TL2 rule.
5. ~~**Additional Slack commands**~~ **Resolved:** `/trust <openmrs-id>`, `/revoke <openmrs-id>`, and `/trust-status <openmrs-id>` — all restricted to the designated private channel.
6. ~~**Notification behavior**~~ **Resolved:** No user notifications in MVP. `slack_notify`, `email`, and `discourse_notify` are deferred as future action types.
7. ~~**Rollback / revocation**~~ **Resolved:** Manual revocation via `/revoke`, triggering `keycloak_remove_groups`. Automatic revocation and writing back to Discourse trust levels are out of scope.
8. ~~**Preferred language/stack**~~ **Resolved:** Python 3.12+ with FastAPI, slack-bolt, python-keycloak, pydiscourse, PyYAML/strictyaml, pytest.
9. ~~**Audit log destination**~~ **Resolved:** SQLite at `/data/audit.db` on a host-mounted Docker volume. See schema in §5.5.
10. ~~**Discourse polling vs. webhooks**~~ **Resolved:** Discourse webhooks and Discourse Workflow HTTP actions, both with signature verification. Replay protection was considered and deliberately not implemented — every action is idempotent, so it's unnecessary.

---

## 9. Current Manual Process (to be replaced)

Per the [Grant Access to new users](https://github.com/openmrs/openmrs-contrib-itsmresources/wiki/Grant-Access-new-users) runbook:

1. ITSM member logs into [Keycloak admin](https://id-new.openmrs.org/admin/) with a user-management admin account
2. Switches to the `OpenMRS` realm
3. Searches for the target username
4. Opens the user → Groups tab
5. Searches for and joins: `jira-trunk-developer`, `jira-users`, `confluence-users`

This manual step is what the OpenMRS Trust Bot automates.

---

## 10. Relevant Infrastructure

- **Infrastructure provider:** OpenStack (Jetstream + OSUOSL)
- **IaC:** Terraform managing VMs running Docker Compose services
- **Keycloak:** `id-new.openmrs.org` — `OpenMRS` realm
- **Discourse:** `talk.openmrs.org`
- **JIRA/Confluence:** Atlassian Cloud (SaaS), access controlled via Keycloak SSO groups
- **Existing chatbots:** There are existing chat bot services in the infrastructure (see [Service-Chat-bots](https://github.com/openmrs/openmrs-contrib-itsmresources/wiki/Service-Chat-bots)) — worth reviewing for patterns/reuse

---

*This document is a living spec. Update as requirements are clarified.*
