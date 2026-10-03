from pathlib import Path

from src.engine.loader import load_rules

EXAMPLE_RULES = Path(__file__).parents[3] / "config" / "rules.example.yaml"


def test_load_rules_parses_example_file():
    rule_set = load_rules(EXAMPLE_RULES)

    names = [rule.name for rule in rule_set.rules]
    assert "Grant community edit access (Discourse TL2)" in names
    assert "Grant community edit access (manual /trust)" in names
    assert "Revoke community edit access (manual /revoke)" in names


def test_load_rules_rereads_file_on_every_call(tmp_path):
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - name: First\n"
        "    enabled: true\n"
        "    triggers:\n"
        "      - type: slack_trust_command\n"
        "    actions:\n"
        "      - type: keycloak_add_groups\n"
        "        groups: [jira-users]\n"
    )

    first = load_rules(rules_file)
    assert [r.name for r in first.rules] == ["First"]

    rules_file.write_text(
        "rules:\n"
        "  - name: Second\n"
        "    enabled: true\n"
        "    triggers:\n"
        "      - type: slack_trust_command\n"
        "    actions:\n"
        "      - type: keycloak_add_groups\n"
        "        groups: [jira-users]\n"
    )

    second = load_rules(rules_file)
    assert [r.name for r in second.rules] == ["Second"]


def test_load_rules_uses_rules_path_env_var(monkeypatch):
    monkeypatch.setenv("RULES_PATH", str(EXAMPLE_RULES))

    rule_set = load_rules()

    assert len(rule_set.rules) == 3


def test_load_rules_logs_path_and_count_at_debug(caplog):
    with caplog.at_level("DEBUG"):
        load_rules(EXAMPLE_RULES)

    messages = [r.message for r in caplog.records]
    assert any("3" in m and str(EXAMPLE_RULES) in m for m in messages)
