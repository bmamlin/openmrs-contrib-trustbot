from slack_bolt.middleware.custom_middleware import CustomMiddleware

from src.audit.db import get_connection
from src.integrations.slack import create_slack_app
from src.ratelimit import RateLimiter


def make_app(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))
    return create_slack_app(
        "xoxb-test-token",
        "test-signing-secret",
        trusted_channel_id="C0123456789",
        audit_conn=conn,
        rate_limiter=RateLimiter(max_requests=1000, window_seconds=60),
    )


def test_create_slack_app_registers_trust_command(tmp_path):
    app = make_app(tmp_path)

    matches_trust_command = any(
        matcher.func({"command": "/trust"})
        for listener in app._listeners
        for matcher in listener.matchers
    )
    assert matches_trust_command is True


def test_create_slack_app_registers_revoke_command(tmp_path):
    app = make_app(tmp_path)

    matches_revoke_command = any(
        matcher.func({"command": "/trust-revoke"})
        for listener in app._listeners
        for matcher in listener.matchers
    )
    assert matches_revoke_command is True


def test_create_slack_app_registers_trust_status_command(tmp_path):
    app = make_app(tmp_path)

    matches_trust_status_command = any(
        matcher.func({"command": "/trust-status"})
        for listener in app._listeners
        for matcher in listener.matchers
    )
    assert matches_trust_status_command is True


def test_create_slack_app_registers_global_rate_limit_middleware(tmp_path):
    app = make_app(tmp_path)

    custom_middleware = [m for m in app._middleware_list if isinstance(m, CustomMiddleware)]
    assert len(custom_middleware) == 1
    assert custom_middleware[0].func.__name__ == "rate_limit_middleware"
