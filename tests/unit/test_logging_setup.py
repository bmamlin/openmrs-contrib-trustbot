import json
import logging

import pytest

from src.logging_setup import configure_logging, redact_headers, redact_slack_body, set_log_level


@pytest.fixture(autouse=True)
def reset_root_logger():
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    yield
    root_logger.handlers = original_handlers
    root_logger.setLevel(original_level)


def test_configure_logging_emits_valid_json_with_expected_keys(capsys):
    configure_logging("INFO")

    logging.getLogger("test.logger").warning("something happened")

    captured = capsys.readouterr()
    line = captured.err.strip() or captured.out.strip()
    record = json.loads(line)

    assert record["level"] == "WARNING"
    assert record["logger"] == "test.logger"
    assert record["message"] == "something happened"
    assert "timestamp" in record


def test_log_level_env_var_overrides_default(monkeypatch, capsys):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging("DEBUG")

    logger = logging.getLogger("test.logger.suppressed")
    logger.info("should be suppressed")
    logger.warning("should appear")

    captured = capsys.readouterr()
    output = captured.err + captured.out
    assert "should be suppressed" not in output
    assert "should appear" in output


def test_blank_log_level_env_var_falls_back_to_default(monkeypatch, capsys):
    monkeypatch.setenv("LOG_LEVEL", "")
    configure_logging("DEBUG")

    logger = logging.getLogger("test.logger.blank_env")
    logger.debug("debug line")

    captured = capsys.readouterr()
    output = captured.err + captured.out
    assert "debug line" in output


def test_set_log_level_takes_effect_immediately(capsys):
    configure_logging("INFO")

    logger = logging.getLogger("test.logger.runtime_change")
    logger.debug("suppressed before change")
    set_log_level("DEBUG")
    logger.debug("visible after change")

    captured = capsys.readouterr()
    output = captured.err + captured.out
    assert "suppressed before change" not in output
    assert "visible after change" in output


def test_set_log_level_rejects_unrecognized_level_and_leaves_level_unchanged():
    configure_logging("INFO")

    with pytest.raises(ValueError):
        set_log_level("VERBOSE")

    assert logging.getLogger().level == logging.INFO


def test_configure_logging_rejects_unrecognized_level():
    with pytest.raises(ValueError):
        configure_logging("VERBOSE")


def test_redact_headers_replaces_authorization_case_insensitively():
    headers = {"Authorization": "Bearer secret-token", "X-Discourse-Event": "user_promoted"}

    redacted = redact_headers(headers)

    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["X-Discourse-Event"] == "user_promoted"
    assert headers["Authorization"] == "Bearer secret-token"  # input untouched


def test_redact_headers_matches_any_case():
    headers = {"authorization": "Bearer secret-token"}

    redacted = redact_headers(headers)

    assert redacted["authorization"] == "[REDACTED]"


def test_redact_slack_body_replaces_token():
    body = {"token": "deprecated-verification-token", "command": "/trust", "text": "jdoe"}

    redacted = redact_slack_body(body)

    assert redacted["token"] == "[REDACTED]"
    assert redacted["command"] == "/trust"
    assert redacted["text"] == "jdoe"
    assert body["token"] == "deprecated-verification-token"  # input untouched
