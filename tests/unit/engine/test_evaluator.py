from src.audit.db import get_connection
from src.engine import evaluator
from src.engine.models import Action, ActionResult, Rule, RuleSet, Trigger, TriggerEvent


def test_registries_are_populated_on_import():
    assert "slack_trust_command" in evaluator.TRIGGER_MATCHERS
    assert "slack_revoke_command" in evaluator.TRIGGER_MATCHERS
    assert "discourse_trust_level" in evaluator.TRIGGER_MATCHERS
    assert "keycloak_add_groups" in evaluator.ACTION_EXECUTORS
    assert "keycloak_remove_groups" in evaluator.ACTION_EXECUTORS


def make_rule(name, trigger_types, *, enabled=True, action_type="keycloak_add_groups"):
    return Rule(
        name=name,
        enabled=enabled,
        triggers=[Trigger(type=t) for t in trigger_types],
        actions=[Action(type=action_type, groups=["jira-users"])],
    )


def test_evaluate_matches_rule_with_multiple_triggers_on_either_one():
    rule = make_rule("multi", ["discourse_trust_level", "slack_trust_command"])
    rule_set = RuleSet(rules=[rule])
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe")

    matched = evaluator.evaluate(rule_set, event)

    assert matched == [rule]


def test_evaluate_skips_disabled_rule():
    rule = make_rule("disabled", ["slack_trust_command"], enabled=False)
    rule_set = RuleSet(rules=[rule])
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe")

    assert evaluator.evaluate(rule_set, event) == []


def test_evaluate_matches_multiple_independent_rules():
    rule_a = make_rule("a", ["slack_trust_command"])
    rule_b = make_rule("b", ["slack_trust_command"])
    rule_set = RuleSet(rules=[rule_a, rule_b])
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe")

    matched = evaluator.evaluate(rule_set, event)

    assert matched == [rule_a, rule_b]


def test_evaluate_unregistered_trigger_type_never_matches():
    rule = make_rule("future", ["github_contribution"])
    rule_set = RuleSet(rules=[rule])
    event = TriggerEvent(type="github_contribution", openmrs_id="jdoe")

    assert evaluator.evaluate(rule_set, event) == []


def test_execute_rule_dispatches_to_registered_executor_and_audits(tmp_path, monkeypatch):
    calls = []

    def fake_executor(action, event, dry_run):
        calls.append((action.type, event.openmrs_id, dry_run))
        return ActionResult(status="success", detail="ok", action_detail='["jira-users"]')

    monkeypatch.setitem(evaluator.ACTION_EXECUTORS, "keycloak_add_groups", fake_executor)

    rule = make_rule("grant", ["slack_trust_command"])
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe", source="alice")
    conn = get_connection(str(tmp_path / "audit.db"))

    results = evaluator.execute_rule(rule, event, conn=conn)

    assert calls == [("keycloak_add_groups", "jdoe", False)]
    assert [r.status for r in results] == ["success"]

    row = conn.execute("SELECT rule_name, trigger_src, status FROM audit_log").fetchone()
    assert row == ("grant", "alice", "success")


def test_execute_rule_passes_dry_run_through_to_executor(tmp_path, monkeypatch):
    calls = []

    def fake_executor(action, event, dry_run):
        calls.append(dry_run)
        return ActionResult(status="dry_run" if dry_run else "success", detail="ok")

    monkeypatch.setitem(evaluator.ACTION_EXECUTORS, "keycloak_add_groups", fake_executor)

    rule = make_rule("grant", ["slack_trust_command"])
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe", source="alice")
    conn = get_connection(str(tmp_path / "audit.db"))

    results = evaluator.execute_rule(rule, event, conn=conn, dry_run=True)

    assert calls == [True]
    assert [r.status for r in results] == ["dry_run"]

    row = conn.execute("SELECT status FROM audit_log").fetchone()
    assert row == ("dry_run",)


def test_execute_rule_records_failure_and_continues_when_executor_raises(tmp_path, monkeypatch):
    def broken_executor(action, event, dry_run):
        raise RuntimeError("boom")

    monkeypatch.setitem(evaluator.ACTION_EXECUTORS, "keycloak_add_groups", broken_executor)

    rule = Rule(
        name="two actions",
        enabled=True,
        triggers=[Trigger(type="slack_trust_command")],
        actions=[
            Action(type="keycloak_add_groups", groups=["jira-users"]),
            Action(type="keycloak_add_groups", groups=["confluence-users"]),
        ],
    )
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe", source="alice")
    conn = get_connection(str(tmp_path / "audit.db"))

    results = evaluator.execute_rule(rule, event, conn=conn)

    assert [r.status for r in results] == ["failure", "failure"]
    assert "boom" in results[0].detail

    rows = conn.execute("SELECT status FROM audit_log").fetchall()
    assert len(rows) == 2


def test_execute_rule_unknown_action_type_is_recorded_as_failure(tmp_path):
    rule = make_rule("unknown action", ["slack_trust_command"], action_type="not_a_real_action")
    event = TriggerEvent(type="slack_trust_command", openmrs_id="jdoe")
    conn = get_connection(str(tmp_path / "audit.db"))

    results = evaluator.execute_rule(rule, event, conn=conn)

    assert results[0].status == "failure"
    assert "not_a_real_action" in results[0].detail
