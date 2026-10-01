import json
import logging

import pytest

from src.logging_setup import configure_logging


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
