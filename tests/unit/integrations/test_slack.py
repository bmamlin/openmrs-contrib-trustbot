from src.audit.db import get_connection
from src.integrations.slack import create_slack_app


def test_create_slack_app_registers_trust_command(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))

    app = create_slack_app(
        "xoxb-test-token",
        "test-signing-secret",
        trusted_channel_id="C0123456789",
        audit_conn=conn,
    )

    matches_trust_command = any(
        matcher.func({"command": "/trust"})
        for listener in app._listeners
        for matcher in listener.matchers
    )
    assert matches_trust_command is True


def test_create_slack_app_registers_revoke_command(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))

    app = create_slack_app(
        "xoxb-test-token",
        "test-signing-secret",
        trusted_channel_id="C0123456789",
        audit_conn=conn,
    )

    matches_revoke_command = any(
        matcher.func({"command": "/revoke"})
        for listener in app._listeners
        for matcher in listener.matchers
    )
    assert matches_revoke_command is True


def test_create_slack_app_registers_trust_status_command(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))

    app = create_slack_app(
        "xoxb-test-token",
        "test-signing-secret",
        trusted_channel_id="C0123456789",
        audit_conn=conn,
    )

    matches_trust_status_command = any(
        matcher.func({"command": "/trust-status"})
        for listener in app._listeners
        for matcher in listener.matchers
    )
    assert matches_trust_status_command is True
