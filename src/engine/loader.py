"""Loads and parses rules.yaml from the mounted /config/ directory.

Per the spec, rules.yaml is re-read from disk on every trigger event so
that rule changes (add/remove/enable/disable) take effect immediately
without restarting the service. config.yaml, by contrast, is loaded once
at startup elsewhere (not in this module).
"""

from __future__ import annotations

from pathlib import Path

from src.engine.models import RuleSet

DEFAULT_RULES_PATH = Path("/config/rules.yaml")


def load_rules(path: Path = DEFAULT_RULES_PATH) -> RuleSet:
    """Read and parse rules.yaml from disk, returning a validated RuleSet.

    Intended to be called fresh on every trigger event (see module
    docstring) rather than cached, so config edits take effect immediately.
    """
    raise NotImplementedError
