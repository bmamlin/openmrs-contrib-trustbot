-- OpenMRS Trust Bot — audit log schema (SQLite)
-- Append-only: the service never updates or deletes rows.
-- See openspec/specs/overview.md §5.5 for the authoritative spec.

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,          -- ISO 8601 UTC
    openmrs_id    TEXT    NOT NULL,          -- target user
    trigger       TEXT    NOT NULL,          -- e.g. 'discourse_trust_level', 'slack_trust_command'
    trigger_src   TEXT,                      -- e.g. Slack username, Discourse webhook URL
    rule_name     TEXT    NOT NULL,          -- matched rule name from YAML
    action        TEXT    NOT NULL,          -- e.g. 'keycloak_add_groups'
    action_detail TEXT,                      -- e.g. JSON list of groups
    status        TEXT    NOT NULL,          -- 'success' | 'no_change' | 'failure' | 'dry_run'
    detail        TEXT                       -- error message or 'no change: already a member' etc.
);
