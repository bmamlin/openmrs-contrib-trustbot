"""Loads and parses rules.yaml from the mounted /config/ directory.

Per the spec, rules.yaml is re-read from disk on every trigger event so
that rule changes (add/remove/enable/disable) take effect immediately
without restarting the service. config.yaml, by contrast, is loaded once
at startup elsewhere (not in this module).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from src.engine.models import RuleSet

logger = logging.getLogger(__name__)


def default_rules_path() -> Path:
    """The rules.yaml path to use when none is given: $RULES_PATH, else /config/rules.yaml."""
    return Path(os.environ.get("RULES_PATH", "/config/rules.yaml"))


def load_rules(path: Path | str | None = None) -> RuleSet:
    """Read and parse rules.yaml from disk, returning a validated RuleSet.

    Intended to be called fresh on every trigger event (see module
    docstring) rather than cached, so rule edits take effect immediately.
    """
    resolved = Path(path) if path is not None else default_rules_path()
    with open(resolved) as f:
        raw = yaml.safe_load(f)
    rule_set = RuleSet.model_validate(raw)
    logger.debug("loaded %d rule(s) from %s", len(rule_set.rules), resolved)
    return rule_set
