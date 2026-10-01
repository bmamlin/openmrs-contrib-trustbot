from pathlib import Path

from src.config import load_config

EXAMPLE_CONFIG = Path(__file__).parents[2] / "config" / "config.example.yaml"


def test_load_config_parses_example_file():
    config = load_config(EXAMPLE_CONFIG)

    assert config.keycloak.realm == "OpenMRS"
    assert config.database.path == "/data/audit.db"
    assert config.discourse.webhook.workflow_name == "trusted"


def test_load_config_uses_config_path_env_var(monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", str(EXAMPLE_CONFIG))

    config = load_config()

    assert config.keycloak.realm == "OpenMRS"
