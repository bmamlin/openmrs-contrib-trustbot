"""/trust, /revoke, /trust-status share one rate limit via create_slack_app()'s
global slack-bolt middleware (see add-rate-limiting design.md).

Exercises the registered middleware function directly (app._middleware_list[0].func)
with constructed `body`/`next`/`ack` stubs, the same way slack-bolt's dispatch()
would kwargs-inject them -- bypassing slack-bolt's HTTP/signature layer, which
is out of scope here and already covered by test_slack.py.
"""

from slack_bolt.middleware.custom_middleware import CustomMiddleware

from src.audit.db import get_connection
from src.integrations.slack import RATE_LIMITED_MESSAGE, create_slack_app
from src.ratelimit import RateLimiter

TRUSTED_CHANNEL = "C0123456789"


def make_middleware(tmp_path, *, max_requests, window_seconds=60):
    conn = get_connection(str(tmp_path / "audit.db"))
    app = create_slack_app(
        "xoxb-test-token",
        "test-signing-secret",
        trusted_channel_id=TRUSTED_CHANNEL,
        audit_conn=conn,
        rate_limiter=RateLimiter(max_requests=max_requests, window_seconds=window_seconds),
    )
    custom_middleware = [m for m in app._middleware_list if isinstance(m, CustomMiddleware)]
    assert len(custom_middleware) == 1
    return custom_middleware[0].func


class _FakeRequest:
    """Minimal stand-in for the BoltRequest slack-bolt would inject as `request`."""

    def __init__(self, headers: dict | None = None):
        self.headers = headers or {}


def invoke(middleware, *, user_id, command):
    acked = {}
    next_called = {"value": False}

    def ack(text=None):
        acked["text"] = text

    def next_func():
        next_called["value"] = True

    middleware(
        body={"user_id": user_id, "command": command},
        next=next_func,
        ack=ack,
        request=_FakeRequest(),
    )
    return acked, next_called["value"]


def test_commands_within_limit_succeed_normally(tmp_path):
    middleware = make_middleware(tmp_path, max_requests=3)

    for command in ("/trust", "/revoke", "/trust-status"):
        acked, next_called = invoke(middleware, user_id="U1", command=command)
        assert next_called is True
        assert acked == {}


def test_exceeding_limit_produces_rate_limited_message_and_skips_next(tmp_path):
    middleware = make_middleware(tmp_path, max_requests=2)

    invoke(middleware, user_id="U1", command="/trust")
    invoke(middleware, user_id="U1", command="/trust")
    acked, next_called = invoke(middleware, user_id="U1", command="/trust")

    assert next_called is False
    assert acked == {"text": RATE_LIMITED_MESSAGE}


def test_limit_is_shared_across_trust_revoke_and_trust_status(tmp_path):
    middleware = make_middleware(tmp_path, max_requests=2)

    first_acked, first_next = invoke(middleware, user_id="U1", command="/trust")
    second_acked, second_next = invoke(middleware, user_id="U1", command="/revoke")
    third_acked, third_next = invoke(middleware, user_id="U1", command="/trust-status")

    assert (first_next, second_next, third_next) == (True, True, False)
    assert third_acked == {"text": RATE_LIMITED_MESSAGE}


def test_different_users_have_independent_counters(tmp_path):
    middleware = make_middleware(tmp_path, max_requests=1)

    _, first_user_next = invoke(middleware, user_id="U1", command="/trust")
    _, second_user_next = invoke(middleware, user_id="U2", command="/trust")

    assert first_user_next is True
    assert second_user_next is True


def test_command_body_logged_at_debug_with_token_redacted_for_allowed_command(tmp_path, caplog):
    middleware = make_middleware(tmp_path, max_requests=3)

    with caplog.at_level("DEBUG"):
        middleware(
            body={"user_id": "U1", "command": "/trust", "token": "deprecated-verification-token"},
            next=lambda: None,
            ack=lambda text=None: None,
            request=_FakeRequest(),
        )

    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("[REDACTED]" in r.message for r in debug_records)
    assert not any("deprecated-verification-token" in r.message for r in debug_records)


def test_command_body_logged_at_debug_with_token_redacted_for_rate_limited_command(tmp_path, caplog):
    middleware = make_middleware(tmp_path, max_requests=0)

    with caplog.at_level("DEBUG"):
        middleware(
            body={"user_id": "U1", "command": "/trust", "token": "deprecated-verification-token"},
            next=lambda: None,
            ack=lambda text=None: None,
            request=_FakeRequest(),
        )

    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("[REDACTED]" in r.message for r in debug_records)
    assert not any("deprecated-verification-token" in r.message for r in debug_records)
