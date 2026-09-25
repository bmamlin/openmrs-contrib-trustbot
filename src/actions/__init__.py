"""Action executors, one module per action type (keycloak_add_groups, keycloak_remove_groups, ...).

`register_all()` populates the engine's ACTION_EXECUTORS registry (see
src/engine/evaluator.py) by type string. Only action types with an actual
implementation are registered here.
"""

from __future__ import annotations


def register_all() -> None:
    from src.actions import keycloak
    from src.engine.evaluator import register_action

    register_action("keycloak_add_groups", keycloak.add_groups)
    register_action("keycloak_remove_groups", keycloak.remove_groups)
